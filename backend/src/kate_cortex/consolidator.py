"""记忆巩固引擎（CONSOLIDATE_PLAN.md / BUTLER_PLAN P1）

「越用越懂你」的核心回路：规则引擎做重要度升降与归档（零 LLM、幂等），
LLM 做重复判定与合并（明显重复自动合并进 .trash 可撤销，矛盾走提案队列）
与画像维护提案（个人信息永不自动改）。拉取式分批（consolidate_pass 每次
处理 ≤limit 对），前端循环调用直到 done。

自主度（BUTLER_PLAN §3 拍板）：破坏性变更永不静默——合并可撤销、冲突与
画像改动全走提案。只动「记忆」「个人信息」两个系统合集。
"""

import json
import logging
import uuid
from datetime import datetime

from .chat.memory import MEMORY_COLLECTION
from .providers.base import Done, TextDelta
from .storage import PROFILE_COLLECTION

logger = logging.getLogger(__name__)

ARCHIVE_COLLECTION = "归档"

# 重要度升降（规则部分）
PROMOTE_MIN_HITS = 3
PROMOTE_WINDOW_DAYS = 30
DECAY_SOFT_DAYS = 90  # 最后活跃超过 → importance cap 2
DECAY_HARD_DAYS = 180  # 超过 → cap 1
ARCHIVE_AFTER_DAYS = 180  # 超过且（调整前）importance ≤2 → 移入「归档」
ARCHIVE_MAX_PER_PASS = 10

# 重复消解
DUPLICATE_SIMILARITY = 0.80  # 与 skills/memory.py、enrich.py 同阈值
CANDIDATE_SCAN_CAP = 300
JUDGED_CAP = 500
PROPOSALS_CAP = 50
DEFAULT_PAIRS = 6

HITS_RETENTION_DAYS = 180


class ConsolidateError(Exception):
    """中止本轮整理的错误（provider 失败等），路由转 400"""


# ── 召回统计 ──


def recall_stats(storage) -> dict[str, dict]:
    rows = storage.conn.execute(
        "SELECT entry_id, COUNT(*) AS hits, MAX(recalled_at) AS last"
        " FROM memory_hits GROUP BY entry_id"
    ).fetchall()
    return {row["entry_id"]: {"hits": row["hits"], "last": row["last"]} for row in rows}


def log_prune_hits(storage, now: datetime) -> int:
    cutoff = _shift_days(now, HITS_RETENTION_DAYS).isoformat(timespec="seconds")
    with storage.conn:
        cursor = storage.conn.execute(
            "DELETE FROM memory_hits WHERE recalled_at < ?", (cutoff,)
        )
    return cursor.rowcount


# ── 重要度升降 + 归档（规则引擎） ──


def adjust_importance(storage, now: datetime) -> list[dict]:
    """每轮至多 ±1，按目标值计算保证幂等（写一次后下轮目标不变则不写）。
    只对「记忆」合集且已有 importance 的条目生效——None 是 P0 enrich 的活"""
    stats = recall_stats(storage)
    actions: list[dict] = []
    for entry in _collection_entries(storage, {MEMORY_COLLECTION}):
        current = entry.importance
        if current is None:
            continue
        hit = stats.get(entry.id)
        if hit:
            days_since_hit = _days_since(hit["last"], now)
            days_active = min(days_since_hit, _days_since(entry.created_at, now))
            promote = (
                hit["hits"] >= PROMOTE_MIN_HITS
                and days_since_hit <= PROMOTE_WINDOW_DAYS
            )
        else:
            days_active = _days_since(entry.created_at, now)
            promote = False
        target = current
        if promote and current < 5:
            target = current + 1
        elif days_active > DECAY_HARD_DAYS:
            target = min(target, 1)
        elif days_active > DECAY_SOFT_DAYS:
            target = min(target, 2)
        if target != current:
            storage.update_entry(entry.id, importance=target)
            actions.append(
                {"entry_id": entry.id, "title": entry.title, "from": current, "to": target}
            )
    return actions


def archive_stale(storage, now: datetime, pre_importance: dict[str, int]) -> list[dict]:
    """久未召回的低重要度记忆移入「归档」合集：退出常驻注入与自动召回，
    仍可搜索、可手动移回。按「调整前」重要度判定——衰减与归档不发生在同
    一轮，给用户一轮的观察窗。每轮 ≤ARCHIVE_MAX_PER_PASS 条"""
    stats = recall_stats(storage)
    actions: list[dict] = []
    for entry in _collection_entries(storage, {MEMORY_COLLECTION}):
        if len(actions) >= ARCHIVE_MAX_PER_PASS:
            break
        if pre_importance.get(entry.id, 3) > 2:
            continue
        last_active = _parse_dt(entry.created_at)
        hit = stats.get(entry.id)
        if hit:
            last_hit = _parse_dt(hit["last"])
            if last_hit and last_active and _ensure_tz(last_hit, now) > _ensure_tz(last_active, now):
                last_active = last_hit
        if last_active is None:
            continue
        if (now - _ensure_tz(last_active, now)).days <= ARCHIVE_AFTER_DAYS:
            continue
        rest = [c for c in entry.collections if c != MEMORY_COLLECTION]
        storage.update_entry(entry.id, collections=[*rest, ARCHIVE_COLLECTION])
        actions.append({"entry_id": entry.id, "title": entry.title})
    return actions


# ── 重复消解（LLM） ──


def duplicate_pairs(storage, proposals: list[dict], judged: list[dict]) -> list[tuple[str, str]]:
    """待判定的相似条目对（已按提案队列/判定缓存过滤），返回 (id_a, id_b)，
    a.created_at ≤ b.created_at。向量不可用时返回空——配对阶段整体跳过"""
    if storage.vectors is None:
        return []
    scope = _scope_rows(storage)
    if not scope:
        return []
    pending_pairs = {
        p["pair"] for p in proposals if p.get("kind") == "conflict" and p.get("pair")
    }
    judged_map = {j["pair"]: j for j in judged}
    pairs: dict[str, tuple[str, str]] = {}
    for entry_id, updated_at in list(scope.items())[:CANDIDATE_SCAN_CAP]:
        try:
            vector = storage.vectors.vector_of(entry_id)
            if vector is None:
                continue
            hits = storage.vectors.query_by_vector(vector, limit=3)
        except Exception as exc:
            logger.warning("邻居查询失败，跳过条目 %s: %s", entry_id, exc)
            continue
        for hit in hits:
            if hit.entry_id == entry_id or hit.entry_id not in scope:
                continue
            similarity = 1.0 - hit.distance
            if similarity < DUPLICATE_SIMILARITY:
                continue
            id_a, id_b = sorted([entry_id, hit.entry_id])
            key = f"{id_a}|{id_b}"
            if key in pairs or key in pending_pairs:
                continue
            seen = judged_map.get(key)
            if seen and seen.get("key") == f"{scope[id_a]}|{scope[id_b]}":
                continue  # 双方 updated_at 都没变，跳过重复判定
            pairs[key] = (id_a, id_b)
    return list(pairs.values())


def judge_pair(storage, provider, entry_a, entry_b) -> dict:
    """LLM 判定两条记忆的关系。返回含 verdict 的 dict（解析失败抛
    ConsolidateError——判定是配对阶段的核心，坏了就该停而非跳过）"""
    prompt = _JUDGE_PROMPT.format(
        ca=entry_a.created_at[:10],
        ta=entry_a.title,
        con_a=entry_a.content[:600],
        cb=entry_b.created_at[:10],
        tb=entry_b.title,
        con_b=entry_b.content[:600],
    )
    data = _parse_llm_json(_call_llm(provider, prompt))
    verdict = data.get("verdict")
    if verdict not in ("duplicate", "update", "conflict", "distinct"):
        raise ConsolidateError(f"判定结果非法: {verdict!r}")
    return data


def merge_pair(storage, entry_a, entry_b, verdict: dict) -> dict:
    """自动合并：保留较早条目为载体，较新条目进 .trash（可撤销）"""
    keywords = list(dict.fromkeys(entry_a.keywords + entry_b.keywords))
    for k in verdict.get("keywords") or []:
        if str(k).strip():
            keywords.append(str(k).strip())
    importance = max(
        entry_a.importance or 3, entry_b.importance or 3, int(verdict.get("importance") or 0)
    )
    storage.update_entry(
        entry_a.id,
        title=str(verdict.get("merged_title") or "").strip() or entry_a.title,
        content=str(verdict.get("merged_content") or "").strip() or entry_a.content,
        keywords=keywords[:8],
        importance=max(1, min(5, importance)),
    )
    storage.delete_entry(entry_b.id)
    return {
        "kind": "merged",
        "kept_id": entry_a.id,
        "kept_title": entry_a.title,
        "trashed_id": entry_b.id,
        "trashed_title": entry_b.title,
        "reason": str(verdict.get("reason") or ""),
    }


# ── 画像维护（LLM，全部提案制） ──


def profile_proposals(storage, provider, since: str | None) -> list[dict]:
    """新记忆中值得并入「个人信息」档案的持久事实 → 提案（不落库）。
    LLM 无话可说时返回空列表"""
    profile = _collection_entries(storage, {PROFILE_COLLECTION})
    memories = _collection_entries(storage, {MEMORY_COLLECTION})
    if since:
        memories = [m for m in memories if m.created_at > since]
    memories = memories[-20:]
    if not memories:
        return []
    profile_blocks = "\n".join(
        f"- {p.id}｜{p.title}：{p.content[:200]}" for p in profile
    ) or "（空）"
    memory_lines = "\n".join(
        f"- {m.created_at[:10]}｜{m.title}：{m.content[:150]}" for m in memories
    )
    prompt = _PROFILE_PROMPT.format(profile=profile_blocks, memories=memory_lines)
    data = _parse_llm_json(_call_llm(provider, prompt))
    out: list[dict] = []
    for item in data.get("updates") or []:
        if item.get("target_id") and item.get("content"):
            out.append(
                {
                    "kind": "profile_update",
                    "target_id": str(item["target_id"]),
                    "title": str(item.get("title") or "").strip(),
                    "content": str(item["content"]).strip(),
                    "reason": str(item.get("reason") or ""),
                }
            )
    for item in data.get("creates") or []:
        if item.get("title") and item.get("content"):
            out.append(
                {
                    "kind": "profile_create",
                    "title": str(item["title"]).strip(),
                    "content": str(item["content"]).strip(),
                    "reason": str(item.get("reason") or ""),
                }
            )
    return out


# ── 编排 ──


def consolidate_pass(storage, settings_service, provider, limit: int = DEFAULT_PAIRS) -> dict:
    now = datetime.now().astimezone()
    settings = settings_service.get_all()
    consolidated_at = settings.get("consolidated_at")
    proposals: list[dict] = settings.get("consolidation_proposals") or []
    judged: list[dict] = settings.get("consolidation_judged") or []

    # 调整前重要度快照：衰减与归档不发生在同一轮
    pre = {e.id: (e.importance or 3) for e in _collection_entries(storage, {MEMORY_COLLECTION})}
    adjusted = adjust_importance(storage, now)
    archived = archive_stale(storage, now, pre)

    merged: list[dict] = []
    conflicts = 0
    pairs = duplicate_pairs(storage, proposals, judged)
    for id_a, id_b in pairs[: max(1, limit)]:
        got_a, got_b = storage.get_entry(id_a), storage.get_entry(id_b)
        if got_a is None or got_b is None:
            continue
        # 合并载体 = 较早条目（id 排序不保证跨日先后，按 created_at 定）
        entry_a, entry_b = sorted(
            [got_a, got_b], key=lambda e: e.created_at or ""
        )
        verdict = judge_pair(storage, provider, entry_a, entry_b)
        if verdict["verdict"] in ("duplicate", "update"):
            judged.append(
                {
                    "pair": f"{id_a}|{id_b}",
                    "key": f"{entry_a.updated_at}|{entry_b.updated_at}",
                    "verdict": verdict["verdict"],
                }
            )
            merged.append(merge_pair(storage, entry_a, entry_b, verdict))
        elif verdict["verdict"] == "conflict":
            # conflict 不进判定缓存：提案被忽略/删除后仍可重新判定，冲突不会被埋没
            conflicts += 1
            proposals.append(
                {
                    "id": _proposal_id(),
                    "kind": "conflict",
                    "created_at": now.isoformat(timespec="seconds"),
                    "pair": f"{id_a}|{id_b}",
                    "a": _proposal_entry(entry_a),
                    "b": _proposal_entry(entry_b),
                    "reason": str(verdict.get("reason") or ""),
                }
            )
        else:
            judged.append(
                {
                    "pair": f"{id_a}|{id_b}",
                    "key": f"{entry_a.updated_at}|{entry_b.updated_at}",
                    "verdict": verdict["verdict"],
                }
            )

    new_profile = profile_proposals(storage, provider, consolidated_at)
    proposals.extend(new_profile)
    proposals = proposals[-PROPOSALS_CAP:]
    judged = judged[-JUDGED_CAP:]

    report = {
        "ran_at": now.isoformat(timespec="seconds"),
        "merged": merged,
        "adjusted": adjusted,
        "archived": archived,
        "conflicts_queued": conflicts,
        "profile_proposals": len(new_profile),
    }
    pruned = log_prune_hits(storage, now)
    settings_service.update(
        {
            "consolidated_at": report["ran_at"],
            "consolidation_report": report,
            "consolidation_proposals": proposals,
            "consolidation_judged": judged,
        }
    )
    remaining = max(0, len(pairs) - max(1, limit))
    return {
        "merged": merged,
        "adjusted": adjusted,
        "archived": archived,
        "conflicts_queued": conflicts,
        "profile_proposals": len(new_profile),
        "pruned_hits": pruned,
        "remaining": remaining,
        "done": remaining == 0,
        "report": report,
    }


# ── 内部 ──


def _scope_rows(storage) -> dict[str, str]:
    """记忆+个人信息条目 {id: updated_at}（DB 直读，避免逐条解析 md）"""
    rows = storage.conn.execute(
        "SELECT e.id, e.updated_at FROM entries e"
        " JOIN entry_collections ec ON ec.entry_id = e.id"
        " JOIN collections c ON c.id = ec.collection_id"
        " WHERE c.name IN (?, ?) ORDER BY e.created_at, e.id",
        (MEMORY_COLLECTION, PROFILE_COLLECTION),
    ).fetchall()
    return {row["id"]: row["updated_at"] for row in rows}


def _collection_entries(storage, names: set[str]):
    out = []
    for row in storage.conn.execute(
        "SELECT DISTINCT e.id FROM entries e"
        " JOIN entry_collections ec ON ec.entry_id = e.id"
        " JOIN collections c ON c.id = ec.collection_id"
        f" WHERE c.name IN ({', '.join('?' * len(names))})"
        " ORDER BY e.created_at, e.id",
        tuple(sorted(names)),
    ):
        try:
            entry = storage.get_entry(row["id"])
        except Exception:
            continue
        if entry is not None:
            out.append(entry)
    return out


def _proposal_entry(entry) -> dict:
    return {
        "id": entry.id,
        "title": entry.title,
        "content": entry.content,
        "created_at": entry.created_at,
    }


def _proposal_id() -> str:
    return f"prop_{uuid.uuid4().hex[:8]}"


def _call_llm(provider, prompt: str) -> str:
    parts: list[str] = []
    try:
        for event in provider.chat_stream(
            [{"role": "user", "content": prompt}], tools=None
        ):
            if isinstance(event, TextDelta):
                parts.append(event.text)
            elif isinstance(event, Done):
                break
    except Exception as exc:
        raise ConsolidateError(f"LLM 调用失败：{exc}") from exc
    return "".join(parts)


def _parse_llm_json(text: str) -> dict:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ConsolidateError("LLM 输出中没有 JSON 对象")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ConsolidateError(f"LLM 输出无法解析：{exc}") from exc


def _days_since(iso: str, now: datetime) -> float:
    moment = _parse_dt(iso)
    if moment is None:
        return 0.0
    return (now - _ensure_tz(moment, now)).total_seconds() / 86400


def _ensure_tz(moment: datetime, now: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=now.tzinfo)
    return moment


def _parse_dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None


def _shift_days(moment: datetime, days: int) -> datetime:
    return datetime.fromtimestamp(moment.timestamp() - days * 86400, tz=moment.tzinfo)


_JUDGE_PROMPT = """你在整理个人记忆库。下面是同一位主人的两条记忆，判断它们的关系。

## 记忆 A（创建于 {ca}）
标题：{ta}
内容：
{con_a}

## 记忆 B（创建于 {cb}）
标题：{tb}
内容：
{con_b}

只输出一个 JSON 对象，不要解释、不要 markdown 代码块：
{{"verdict": "duplicate|update|conflict|distinct", "merged_title": "…", "merged_content": "…", "keywords": ["…"], "importance": 3, "reason": "…"}}

判定标准：
- duplicate：两条说的是同一件事，信息无增量 → 合并；
- update：B 是 A 的新进展（同一事实的时间线推进）→ 合并，merged_title/merged_content
  以最新信息为准，保留仍有价值的旧细节；
- conflict：两条相互矛盾且无法确定哪个最新（如「住在杭州」vs「住在北京」）→ 不合并；
- distinct：话题相似但实为不同事实 → 不合并；
- merged_title / merged_content / keywords / importance 仅 duplicate、update 需要：
  keywords 为 3-8 个场景触发词（将来聊到什么话题该想起它），importance 取两条中较高者；
- reason：一句话判定依据。"""

_PROFILE_PROMPT = """你在维护主人的「个人信息」档案——这是 AI 对主人的核心认知
（身份、长期偏好、健康基线、重要关系），每条一个主题。根据新记忆，找出值得
并入档案的持久事实：合并进已有条目（给出合并后的完整内容）或建议新建条目。
临时状态（感冒中、最近在赶项目）不是档案。没有值得并入的就输出空列表。

只输出一个 JSON 对象，不要解释：
{{"updates": [{{"target_id": "…", "title": "…", "content": "…", "reason": "…"}}],
  "creates": [{{"title": "…", "content": "…", "reason": "…"}}]}}

## 现有档案
{profile}

## 新记忆
{memories}"""
