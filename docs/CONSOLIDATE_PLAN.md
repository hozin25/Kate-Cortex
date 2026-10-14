# P1 记忆巩固引擎：去重合并 / 重要度升降 / 画像维护 / 归档

> **状态：已实施（2026-10-14）**。BUTLER_PLAN.md §5 的细化设计。
> 目的：供实施按本文档逐项落地，不依赖撰写时的会话上下文。
> 决策依据（BUTLER_PLAN §3）：混合自主度——明显重复自动合并 + 报告可撤销；
> 新旧冲突、画像改动作提案，逐条确认。边界：只动「记忆」「个人信息」两个
> 系统合集，不碰知识库文档；归档是降权不是删除。

---

## 0. 一句话概述

`POST /api/consolidate/run` 拉取式分批整理：规则引擎做**重要度升降**与**归档**
（零 LLM 成本、幂等），LLM 做**重复判定与合并**（明显重复自动合并进 .trash 可撤销，
矛盾走提案队列）与**画像维护提案**；全过程产报告，前端循环调用直到完成。

## 1. 召回埋点（db v7：memory_hits 表）

知识引用有 `messages.knowledge_refs` 可统计，但**记忆召回没有记录**
（`chat/agent.py` 只把 RAG snippets 写入 knowledge_refs）。补一张轻量日志表：

```sql
CREATE TABLE IF NOT EXISTS memory_hits (
  entry_id   TEXT NOT NULL,
  recalled_at TEXT NOT NULL,
  source     TEXT            -- resident | recall
);
CREATE INDEX IF NOT EXISTS idx_memory_hits_entry ON memory_hits(entry_id, recalled_at);
```

- 写入点两处：`routes/chat.py` 常驻注入后（source=resident）、
  `skills/memory.py` recall_memory 命中后（source=recall）；失败只告警；
- 清理：每次整理跑完 `DELETE WHERE recalled_at < now-180d`。
- 纯增量日志，不参与任何读取路径，丢数据无害。

## 2. 重要度升降（规则引擎，幂等）

仅「记忆」合集（个人信息由画像维护负责，避免画像条目被衰减挤出常驻注入）。
以 `max(最近召回, created_at)` 为最后活跃时间：

| 条件 | 动作 |
|---|---|
| 召回 ≥3 次且最近召回在 30 天内且 importance < 5 | +1（每轮至多 1，写入即停） |
| 最后活跃 >90 天 | 目标 cap 2（仅当当前 >2 时写入） |
| 最后活跃 >180 天 | 目标 cap 1 |
| >180 天且 importance ≤2 | **归档**：移出「记忆」进「归档」合集（每轮 ≤10 条） |

幂等关键：升降按「目标值」计算（>90d → cap2），写一次后下轮目标不变则不写，
无需 per-entry 状态。归档后条目退出常驻注入与 recall（不在「记忆」合集），
仍在知识库可搜索——降权不是删除。

## 3. 重复消解（LLM 判定，混合自主）

1. **候选对**：向量可用时，对「记忆+个人信息」条目逐个 `vectors.query(top3)`，
   sim ≥0.80 组成无序对（排除已在提案队列/已判定缓存中的对）；
2. **判定**（每对一次 LLM）：输入两条的标题/正文/创建时间，输出 JSON
   `{verdict: duplicate|update|conflict|distinct, merged_title, merged_content,
   keywords, importance, reason}`；
   - **duplicate / update → 自动合并**：保留较早条目（created_at 在前）为载体，
     按判定结果更新（keywords 取并集 ≤8、importance 取最大），较新条目
     `delete_entry` 进 `.trash`（30 天可恢复）；动作记入报告，前端可一键
     「撤销」（= restore_entry 恢复被合并条目）；
   - **conflict → 提案队列**：卡片展示两条冲突记忆，用户选「保留较新 /
     保留较旧」，采纳即另一种进 .trash；
   - **distinct → 判定缓存**：settings `consolidation_judged` 记
     `pair键 + 双方 updated_at`，两者都没改过就不再重复判定（省 LLM 费）；
3. 每轮判定 ≤`limit`（默认 6，≤12）对，剩余数随响应返回，前端循环。

## 4. 画像维护（LLM，全部走提案）

个人信息是对外注入的核心认知（user_profile 常驻前 3 条），**不自动改**。
自上次整理以来的新「记忆」（≤20 条）+ 现有画像条目交 LLM，输出
`updates: [{target_id, title, content, reason}]` 与
`creates: [{title, content, reason}]`，全部进提案队列，采纳时才落库
（update_entry / create_entry(collections=[个人信息])，source=manual）。

## 5. 状态存储与 API

settings KV 存 `consolidated_at` / `consolidation_report` / 
`consolidation_proposals`(≤50) / `consolidation_judged`（内部状态，不走
SettingsOut/PUT）。提案 id = `prop_` + 8 位 hex。

```
GET    /api/consolidate/status              {consolidated_at, report, proposals,
                                            candidates, vector_available}
POST   /api/consolidate/run   {limit≤12}    一轮整理 → {merged, conflicts_queued,
                                            adjusted, archived, profile_proposals,
                                            remaining, done, report}
POST   /api/consolidate/proposals/:id/accept {keep?: "a"|"b"}   按 kind 分发
DELETE /api/consolidate/proposals/:id        忽略提案
POST   /api/consolidate/undo/:entry_id       restore_entry 恢复被合并条目
```

provider 走默认会话模型；构建/调用失败 → ConsolidateError → 400（前端停循环）。
候选扫描上限 300 条目（个人规模内 KNN 开销可忽略）。

## 6. 前端（MemoriesPage 顶部「整理记忆」面板）

- 状态行：上次整理时间 + 待判定对数徽标 +「整理记忆」按钮（循环跑，
  进度 `整理中 x/y`）；
- 报告区：合并列表（每项带「撤销」）、重要度调整 n 条、归档 n 条、新提案 n 条；
- 提案卡：conflict（两条记忆 + 保留较新/较旧按钮）、profile_update（diff 展示 +
  采纳/忽略）、profile_create（采纳/忽略）；
- 触发时机：手动按钮为主；面板在页面加载后展示状态提示（不在后台自动跑，
  避免启动即产生 LLM 费用——对 BUTLER_PLAN「启动检查后台跑」的收窄，见 §8）。

## 7. 测试

`backend/tests/test_consolidate.py`：升降/归档规则与幂等（直接插 memory_hits）、
合并（FakeProvider 判定 duplicate → 旧条目更新 + 新条目进 .trash + 报告 + undo
恢复）、conflict 提案 accept(keep=a/b)/dismiss、distinct 缓存跳过、画像提案
accept 落库、向量不可用跳过配对阶段、memory_hits 写入与清理、API 注入 fake。
前端：MemoriesPage 测试补 consolidate/status mock 默认实现，新增面板渲染用例；
`lib/consolidate.ts` 循环单测（复用 enrich 循环测试手法）。

## 8. 与 BUTLER_PLAN §5 的偏差记录

- 「应用启动检查后台跑」收窄为「记忆页展示待整理状态 + 手动一键跑」：
  后台自动跑会在用户无感知时产生 LLM 费用，与混合自主度精神冲突；
- 重要度调整范围收窄到「记忆」合集（个人信息交给画像维护）；
- 冲突提案提供「保留较新/较旧」双向选择，而非固定建议。

## 9. 边界（明确不做）

- 不做语义级「记忆合并成画像」的全自动（提案制）；不做跨合集去重
  （知识库文档不参与）；无向量时跳过配对阶段（其余阶段照常）；
- 归档合集不做独立页面（条目仍在知识库页可见可搜索）。
