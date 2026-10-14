# P2 管家人设 + 每日简报（BUTLER_PLAN §6 细化设计）

> **状态：已实施（2026-10-14）**。目标：懂你且会主动开口。

## 1. 管家人设（chat/prompts.py PERSONA）

默认人设从「个人知识助手」升级为私人管家：可靠、主动、有分寸；记得用户的事
（记忆/档案已注入），涉及健康/日程/偏好时主动关联（一句点到为止），发现可能
被忽略的事主动提醒。**工具规则（TOOL_RULES 等）零改动**——人格可换，能力不裁；
自定义 agent 的叠加覆盖机制不变（/医生 仍是医生）。

## 2. 每日简报（backend/src/kate_cortex/briefing.py）

`GET /api/briefing?refresh=false`：

- **数据**：「记忆」合集 top30（importance/recency 序）+「个人信息」前 6 条 +
  今天日期与星期；
- **生成**：一次 LLM 调用输出 `{greeting, items:[{kind, text, entry_id}]}`，
  kind ∈ due（今日/近日到期或已过期日程）/ followup（进行中值得跟进）/
  tip（基于记忆的主动建议，≤1 条）；提示词强约束：只能引用给定条目、
  entry_id 必须原样来自列表、没有时间敏感项不得编造；
- **校验**：kind 白名单、entry_id 不在列表则置空、text 非空、items ≤6；
- **缓存**：settings `briefing_cache` = {date, payload}——同一天不重复调 LLM，
  `refresh=true` 强制重生成；写缓存只在成功后；
- **降级**：无记忆条目 → 静态管家问候，不调 LLM；memory_enabled 关 → 同上；
  provider 失败 → 400（前端静默隐藏卡片，不 toast 轰炸）。

## 3. 前端（BriefingCard @ ChatPage）

- 位置：对话页消息流顶部（随消息流滚动）；当日已读（localStorage
  `kate_briefing_dismissed` = 日期）则不拉取不展示；
- 卡片：极光描边玻璃卡 +「M月D日 · 管家简报」+ greeting + 分条目（图标按
  kind 区分）+ 关闭按钮；
- **系统通知**：拉取成功后对 due 项发一条系统通知（`new Notification`，
  仅在权限已 granted 时发，不主动索权；jsdom/不支持环境静默跳过）。

## 4. 测试

后端 `test_briefing.py`：同日缓存命中（fake.calls==1）/ refresh 强制重生成、
无记忆不调 LLM、非法 entry_id 被剔除、memory_enabled 关闭走静态、API 400。
前端 `BriefingCard.test.tsx`：渲染 items、关闭写 localStorage（当日不再拉取）、
无 Notification 环境不报错。

## 5. 偏差记录（对 BUTLER_PLAN §6）

- 「主动提醒」由渲染进程在拉取简报时触发系统通知，**不做** Electron 主进程
  定时轮询（应用不开就无提醒——桌面应用的诚实边界；常驻后台留给后续需求）；
- 简报入口固定在对话页顶部，不做独立首页。
