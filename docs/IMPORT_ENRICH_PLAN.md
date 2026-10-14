# P0 导入加工流水线：import 条目 LLM 补齐 keywords / importance / 合集 + 重复标记

> **状态：已实施（2026-10-14）**。BUTLER_PLAN.md §4 的细化设计。
> 目的：供实施按本文档逐项落地，不依赖撰写时的会话上下文。
> 背景：`importer.py` 原样搬运 md，导入条目没有 keywords/importance/合集归属，
> 检索打分吃亏（recall 关键词重合 ×3、向量通道都依赖 keywords）——导进来的
> 是「死记忆」。本流水线在导入后补一层 LLM 加工，让存量数据即导即用。

---

## 0. 一句话概述

新增 `POST /api/import/enrich` 分批加工端点：每批取 ≤N 条 `source=import` 且缺
keywords/importance 的条目，逐条调 LLM 生成缺失元数据并写回（md + SQLite 双写，
走 `storage.update_entry`），同时用向量查重标记疑似重复（只标记不合并，合并留给
P1 巩固引擎）。前端导入面板自动循环调用直到加工完毕，可随时中断、可重跑。

## 1. 关键取舍：拉取式分批端点，而非后台线程

| 方案 | 结论 |
|---|---|
| 后台线程在 sidecar 里跑 | ❌ 单进程共享 sqlite 连接，并发游标错乱有前科（commit fae47bf）；长任务与请求线程抢连接风险真实存在；还要自建进度状态与多用户隔离 |
| 导入请求内联加工 | ❌ 几百条 × 每条一次 LLM 调用，单请求几十分钟必超时 |
| **拉取式分批（采用）** | ✅ `POST /import/enrich {limit}` 每次加工一小批即返回 `{processed, remaining, ...}`；前端循环调用直到 remaining=0。天然幂等可续跑、进度免费、零后台态、多用户无感（走 get_services）、失败重跑无副作用 |

「导入后自动加工」因此是**前端行为**：设置 `import_enrich` 开（默认开）且导入非
dry_run 时，导入完成后前端自动开跑循环。后端不感知该开关（开关只控制自动启动，
「补加工」按钮任何时候可用）。

## 2. 待加工条目的选取（幂等关键）

```sql
SELECT id FROM entries
 WHERE source = 'import'
   AND (keywords IS NULL OR keywords = '' OR importance IS NULL)
 ORDER BY created_at, id
 LIMIT ?   -- remaining 用同一 WHERE 做 COUNT(*)
```

- 只碰 `source='import'`：手动/chat 来源的条目即使缺 keywords 也不动（用户手写
  的空字段是「没填」不是「要补」）；vault 导入的 Kate 格式条目自带字段自然不在列；
- **已有哪些就补哪些，不覆盖已有**：`need_keywords = not entry.keywords`、
  `need_importance = entry.importance is None`，已有 keywords 只补 importance 时
  提示词不要求 keywords，写回时 `update_entry(keywords=None)` 保持原值；
- 文件缺失的坏条目 `get_entry` 抛错 → 记入 skipped 继续下一批；因仍满足 WHERE 会
  重复出现在待选里，由前端循环上限（100 轮）兜底防死循环（坏条目属罕见态，
  sync 页有专门报告）。

## 3. LLM 加工（`enrich.py`）

### 3.1 调用方式

对齐 `summarizer.py` 范式：`provider.chat_stream([{role, content}], tools=None)`
收集 `TextDelta`。provider 由路由层构建：`provider_factory(settings["default_provider"])`
（即默认会话模型；`ProviderError` → 400，前端据此停止循环并提示）。

### 3.2 提示词（按需拼装，中文固定，正文跟随条目语言输出关键词）

```
你在给个人知识库的一条导入条目生成检索元数据。只输出一个 JSON 对象，
不要解释、不要 markdown 代码块。

条目标题：{title}
条目正文：
{content 截断 1200 字}

现有合集列表：{names or （空）}

输出字段要求：
{"keywords": ["…"], "importance": N, "collection": "…"}
- keywords：{3-8 个场景触发词——将来聊到/搜到什么话题时应该想起这条内容，
  做同义词与场景联想，不限于文中原词；用条目主要语言}   ← 仅 need_keywords 时出现
- importance：{1-5 整数。随手收藏 1-2，日常参考资料 3，对生活有实际影响的
  （健康/日程/重要偏好/花费）4-5}                        ← 仅 need_importance 时出现
- collection：{从现有合集列表中选一个最贴题的；确实都不合适才起新名（≤6 字）；
  拿不准给 ""}                                            ← 仅条目当前无合集时出现
```

### 3.3 解析与校验（宽松容错）

- 剥 ``` 代码围栏后取首个 `{` 到末个 `}` 做 `json.loads`；失败 → skipped（原因：
  LLM 输出无法解析），条目不动、下批重试；
- keywords：str 列表、去空去重、截 8 个；非法 → 按缺失处理；
- importance：int 强转，钳到 1-5；非法 → 按缺失处理；
- collection：strip 后非空才采用。

### 3.4 写回与重复标记

- 写回一律走 `storage.update_entry`（md/DB/FTS/向量四路同步，无需新代码路径）：
  `keywords=`（仅 need_keywords）、`importance=`（仅 need_importance）、
  `collections=[*当前, suggestion]`（**仅条目当前无合集**时；已有 tags 的条目合集
  不动——tags 已是用户的组织意图，避免 LLM 噪声合集覆盖）；
- 重复标记（只报告不合并，P1 消化）：`storage.vectors` 可用时以
  `title\n\ncontent[:400]` 查 top3，`similarity = 1 - distance ≥ 0.80`（与
  `skills/memory.py` DUPLICATE_SIMILARITY 同阈值）且 id ≠ 自身、条目仍存在，
  取前 2 条记 `{entry_id, title, similarity}`；向量不可用静默跳过。

### 3.5 失败语义分级

| 层级 | 情形 | 行为 |
|---|---|---|
| abort（EnrichError） | provider 构建失败 / 流式调用抛错（无 key、网络、限流） | 中止整批上抛 → 路由 400，前端停止循环并 toast |
| skip（可重试） | JSON 解析失败 / 字段非法 / md 文件缺失 | 该条记入 skipped，继续批内下一条，下次调用重试 |

## 4. API

```
POST /api/import/enrich   {limit?: int = 8}   → EnrichOut
EnrichOut = {
  processed: int,            # 本批成功加工数
  remaining: int,            # 剩余待加工数（加工完为 0）
  done: bool,                # remaining == 0
  enriched: [{entry_id, title, keywords, importance, collection, duplicates: [...]}],
  skipped: [str],            # 「slug：原因」
}
```

- 路由加在 `routes/importer.py`（同域）；`limit` ge=1 le=24（单请求时长控制在
  ~1 分钟内）；
- models.py 增 `EnrichIn` / `EnrichDuplicateOut` / `EnrichItemOut` / `EnrichOut`。

## 5. 设置开关

| 位置 | 改动 |
|---|---|
| `settings.py` DEFAULTS | `"import_enrich": True` |
| `models.py` | `SettingsUpdate.import_enrich: bool \| None` + `SettingsOut.import_enrich: bool`（extra=forbid，缺一 PUT 即 422/被过滤） |
| 前端 `types.ts` | `AppSettings.import_enrich: boolean` |
| UI | 「数据导入」面板加 ToggleSwitch「导入后自动加工」（走现有 handleSave）+「补加工」按钮 |

## 6. 前端

- 新增 `lib/importEnrich.ts`：`runEnrichLoop({ api, limit, maxRounds, onProgress })`
  纯循环逻辑（remaining>0 且轮数未超上限就继续），独立成模块以便 vitest 单测；
- `SettingsPage.tsx` 数据导入面板：
  - 自动加工 ToggleSwitch；
  - 「补加工」按钮：跑循环，按钮内 Spinner + 「加工中 x/y」进度文案，结束 toast
    汇总（成功 n、跳过 m、疑似重复 k），结果并入下方报告区；
  - `runImport` 成功（非 dry_run）且 `settings.import_enrich` → 自动接续跑循环
    （toast 提示「开始自动加工」）。

## 7. 测试

**后端** `backend/tests/test_enrich.py`（单测直调 enrich_batch + FakeProvider 脚本；
API 用例 `client.app.state.provider_factory = lambda name, model=None: fake` 注入）：

1. 选取：import 条目被加工、manual/chat 不动；写回验证 get_entry（md frontmatter +
   DB 值）；batch=1 分批推进；
2. 只缺 importance 时已有 keywords 保留（FakeProvider 断言收到的 prompt 不含
   keywords 要求、update 后原 keywords 不变）；
3. 坏输出（非 JSON / 字段非法）→ skipped、条目未动、remaining 不减；
4. 合集：无合集条目采纳建议（新名自动建合集）；已有合集条目合集不动；
5. 重复标记：vector_storage 夹具同语义簇两条 → duplicates 命中 similarity=1.0；
6. 幂等：全加工完后再次调用 processed=0 / remaining=0 / done=true；
7. API：注入 fake → 200 且条目加工；provider 抛 ProviderError → 400；
8. 设置：PUT import_enrich=false → GET 回读 false。

**前端** `lib/importEnrich.test.ts`：mock api 依次返回 remaining 递减 → 循环次数与
汇总正确；中途抛错 → 异常上抛且不再调用；maxRounds 兜底。

**收尾基线**：`cd backend && uv run pytest`；
`cd frontend && pnpm typecheck && pnpm lint && pnpm test`。

## 8. 文档同步（收尾提交）

- `docs/DESIGN.md`：§4.1 端点表加 `/api/import/enrich`；设置键清单补 `import_enrich`；
- `README.md` 核心特性补一条「导入自动加工」；
- `docs/BUTLER_PLAN.md` §4 标注已实施并指向本文档。

## 9. 边界（明确不做）

- 不做自动合并/去重决策（P1）；不做 dry_run 预览（加工本身低风险且可重跑）；
- 不做后台定时加工（拉取式，前端驱动）；不碰非 import 来源条目；
- 不生成摘要/改标题/改正文——正文加工属未来需求，v1 只补元数据。
