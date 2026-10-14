# P3 全局速记（一键闪记）+ 视觉（BUTLER_PLAN §7 细化设计）

> **状态：已实施（2026-10-14）**。复刻小布最被称道的「随手一记」：
> 任何应用里想到什么 → 全局热键唤起速记窗 → Ctrl+Enter → 落库即加工。

## 1. 后端 `POST /api/capture`

- 正文即记忆：`create_entry(source="manual", title=首个非空行截 40 字)` +
  **内联单条加工**（`enrich.enrich_one`，P0 重构暴露）：keywords/importance/
  合集归属一步到位；
- **加工是 best-effort**：provider 缺 key / 输出异常 → 条目照常入库，响应
  `enriched=false` + `hint` 原因（绝不因加工失败丢内容）；空文本 422；
- enrich_batch 同步重构为「选批 + enrich_one 单条」，行为不变（测试回归）。

## 2. Electron 主进程（frontend/src/main/index.ts）

- `globalShortcut.register('CommandOrControl+Shift+K')` 切换速记窗（占用时
  console.warn 降级，不影响启动）；与应用内 Ctrl+K（知识库搜索）不冲突；
- 速记窗：460×360 无边框、置顶、不进任务栏，加载同一 renderer 的
  `#/capture` 路由（api token 经 additionalArguments 同主窗口机制注入）；
- 窗口语义：「关闭」= 隐藏（close 事件拦截），热键随时再唤起；**主窗口关闭
  → 销毁速记窗**（否则 window-all-closed 不触发，应用会隐形驻留）；
  `will-quit` 置 quitting 标志放行关闭并 `unregisterAll()`。

## 3. 渲染层 CapturePage（#/capture，无侧栏壳）

- textarea 自动聚焦；Ctrl/⌘+Enter 保存；Esc 关闭（=隐藏）；
- 保存成功 toast「已记下：标题」，清空并关窗；失败 toast 错误保留内容；
- App.tsx 按 `pathname === '/capture'` 渲染无壳分支（跳过 AuthGate 侧栏布局，
  ToastHost 保留）。

## 4. 视觉

科技感落在**已有行为的质感**上：简报卡极光描边（P2 已做）、速记窗深色玻璃 +
space-bg 星空底；不做全应用视觉重构（等真实使用反馈再迭代）。

## 5. 测试

后端 `test_capture.py`（内联加工/标题截断/缺 key 与坏输出仍入库/空文本 422）
+ `test_enrich.py` 重构回归。前端 `CapturePage.test.tsx`（Ctrl+Enter 提交、
成功关窗、Esc 关闭、空文本不提交）。

## 6. 边界

不做剪贴板监听/自动抓取选中文字（需无障碍权限且易误触，热键+手贴已够顺手）；
速记不进「记忆」合集（是否为生活记忆交给加工阶段建议合集时判断）；
不做图片速记（视觉链路走对话页发图）。
