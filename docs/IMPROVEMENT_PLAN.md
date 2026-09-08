# 改进规划：第一梯队四件套 + 第二梯队六项

> **状态（2026-09-08）**：IMP-1 ~ IMP-10 全部实施完成，详见 IMPLEMENTATION_PLAN.md 阶段 13。

> 目的：供**新任务**按本文档逐项实施，不依赖原会话上下文。
> 撰写：2026-09-07 · 依据：竞品分析收尾后的剩余改进清单
> 范围：IMP-1~4（第一梯队，低成本高感知）+ IMP-5~10（第二梯队，工作流补齐）

---

## 0. 实施前必读

1. **先看并行开发**：本仓库存在多会话并行开发史（git log 里 vector/mcp/p0/packaging
   等提交来自不同会话）。开工前先 `git log --oneline -20` + `git status`，确认
   工作区干净、了解最新进展；本文档的"现状锚点"以撰写时为准，若相关文件已变，
   以实际代码为准并顺手更新本文档。
2. **基线**：开工先跑 `cd backend && uv run pytest` 与
   `cd frontend && pnpm typecheck && pnpm lint && pnpm test`，确认全绿再动手；
   每项收尾复跑。撰写时基线：后端 342 / 前端 25（会漂移，以当时实际为准）。
3. **House rules（都是踩过的坑）**：
   - 前端新页面数据加载用 **promise 链**（`.then(setState)`）而非 async 函数
     ——react-hooks v7 的 `set-state-in-effect` 规则会拦 async 版；
   - 渲染进程所有 HTTP **必须走 `api/client.ts`**（自动带 `X-Kate-Token` 鉴权头），
     裸 fetch 会被本地鉴权中间件 401；
   - 测试里 mock 模块用 `vi.hoisted(() => ({...}))` 定义 mock 对象再进 `vi.mock` 工厂；
   - **不要用 PowerShell `Set-Content` 写含中文/BOM 敏感文件**（会写坏 UTF-8），
     改文件一律用编辑器/Node/Python 显式 utf-8；
   - 每项独立提交，提交点文案见各节；`.zcode/` 目录不入库。
4. **架构速览（找文件用）**：
   - 后端 `backend/src/kate_cortex/`：`main.py`(FastAPI 装配+鉴权中间件) ·
     `storage.py`(md↔SQLite 双写) · `chat/agent.py`(SSE agent loop) ·
     `chat/memory.py`(记忆召回) · `chat/rag.py`(FTS+向量 RRF 混合检索) ·
     `vectors.py`(sqlite-vec 索引) · `security.py`(DPAPI) · `mcp_server.py`
   - 前端 `frontend/src/renderer/src/`：`pages/`(Chat/Library/Memories/Trash/
     EntryDetail/EntryEdit/Settings) · `stores/`(zustand: chat/library/settings/toast) ·
     `api/client.ts`+`api/sse.ts`
   - Electron 主进程 `frontend/src/main/`：`index.ts`(启动时序) · `sidecar.ts`
     (后端子进程管理，含自动重启) · `preload/index.ts`(传端口+token)

---

## IMP-1 发送前图片压缩（第一梯队）

**现状**：`ChatInput.tsx` 把文件读成 data URL 原样发送；后端限制单张 5MB，
且多模态历史每轮重发图片——大图直接吃 token 和延迟。

**方案**（纯前端）：
- 新增 `frontend/src/renderer/src/lib/imageCompress.ts`：
  `compressImage(file: File): Promise<string>`——gif 直接透传（canvas 会丢动画）；
  其余用 `createImageBitmap` + canvas 缩放，**最长边 ≤1568px**、输出 JPEG
  quality 0.85（PNG 截图压成 JPEG 体积通常降 80%+）；原图最长边已 ≤1568
  且 <300KB 时透传。
- `ChatInput.tsx` 的 `readAsDataUrl` 替换为 `compressImage`（保持接口不变，
  乐观渲染/后端落盘链路零改动）。
- 拍板：不引入新依赖，用原生 canvas。

**验收**：贴一张 2000px 截图，Network 里请求体明显变小；聊天里图片清晰度
可接受；gif 动图不失动画。单测对 helper 做边界（gif 透传、小图透传），
canvas 逻辑 jsdom 不可测、走人工验证。

**提交点**：`feat: client-side image compression for chat`

## IMP-2 Ctrl+K 全局搜索（第一梯队）

**现状**：`App.tsx` 的 `GlobalShortcuts` 只处理 Ctrl+N；知识库搜索框在
`LibraryPage`，无快捷入口。计划书 5.3 挂账。

**方案**：
- `GlobalShortcuts` 加 `Ctrl+K` → `navigate('/library')` + 触发聚焦信号。
- 聚焦信号：`libraryStore` 加 `focusSearchTick: number` + `requestFocusSearch()`
  action；`LibraryPage` 用 `useEffect([focusSearchTick])` 聚焦搜索框并把 tick 清零。
  （不走 URL 参数，避免和现有 collection 查询参数耦合。）
- 仅应用内快捷键（renderer keydown），不注册 OS 级 globalShortcut（会全局抢键）。

**验收**：任意页面 Ctrl+K → 跳知识库且光标在搜索框；连续按不产生副作用。

**提交点**：`feat: ctrl+k global search focus`

## IMP-3 亮色主题（第一梯队）

**现状**：仅暗色。色彩散布在两处：`assets/styles.css` 的 oklch tokens +
`.space-bg`/`.glass*` 类，和大量 `text-zinc-*`/`bg-ink-*` Tailwind 工具类。
DESIGN §8.2 声称支持 `.dark` 切换——从未实现，本次兑现并同步文档措辞。

**方案**（分两层，先 tokens 后清扫）：
1. `styles.css`：把背景/表面/边框的核心值收敛为 CSS 变量（`--kc-bg`、
   `--kc-surface`、`--kc-border`、`--kc-text`…），`html[data-theme="light"]`
   覆盖一组亮色值（space-bg 改浅色渐变、glass 改白底半透明+深色描边）。
2. 逐页把最刺眼的硬编码暗色（`bg-ink-950/60`、深色 border、`text-zinc-*`
   的低对比组合）替换为变量或 Tailwind 任意值 `bg-[var(--kc-surface)]`。
   **不强求一次替换所有 zinc 类**——正文 `text-zinc-100/300/400` 在亮底上
   换 `--kc-text` 系即可，工作量集中在 Chat/Library/Memories/Settings 四页。
3. 切换 UI：SettingsPage 顶部「外观」区块（暗/亮两选一）；状态存
   `localStorage('kc-theme')`，`main.tsx` 渲染前读并设 `document.documentElement
   .dataset.theme`（避免闪白）。
4. 代码块 shiki 主题保持 tokyyo-night（代码块深色在亮色主题里是常见做法，
   拍板不改）。

**验收**：切换即时生效且刷新后保持；四个主页面亮色下无不可读文本/黑洞背景。

**提交点**：`feat: light theme with appearance setting`

## IMP-4 应用图标（第一梯队）

**现状**：`frontend/resources/icon.png` 与 `build/` 均为 electron-vite 模板图标；
安装包/任务栏无品牌感。

**方案**：
- 生成 512×512 品牌图：深色圆角底 + 蓝紫渐变（对齐 aurora-indigo→aurora-violet）
  字母 "K"（或 "KC"），SVG 手写后用任一栅格化工具出 png（可用
  `pnpm exec sharp`/在线工具/shiki 无关的小脚本，不强求工具链）。
- 放置：`frontend/build/icon.png`（≥256px，electron-builder 自动转 .ico）+
  替换 `frontend/resources/icon.png`（窗口/ docks 用）。
- `electron-builder.yml` 的 `directories.buildResources: build` 已指向 build/，
  无需改配置；重打安装包验证。
- 拍板：图标是个人品牌 MVP，不请设计，后续想换随时换文件。

**验收**：重新 `electron-builder --dir` 后 win-unpacked 的 exe 资源图标、
任务栏图标、安装向导图标均为新图。

**提交点**：`feat: brand app icon`

## IMP-5 Obsidian vault 导入器（第二梯队）

**现状**：无任何导入能力。本项目 frontmatter 与 Obsidian 高度兼容，但有三处
差异要处理：① Obsidian 的 `tags` → 我们的合集（唯一组织机制）；② Obsidian
`[[链接]]` 指向**文件名**，我们指向 **slug**，必须重写；③ Obsidian 附件引用
`![[pic.png]]` 语法不同且附件在 vault 内任意位置。

**方案**：
- 后端新增 `importer.py` + `POST /api/import/obsidian`
  `{source_dir, tags_as_collections=true, dry_run}`：
  1. 扫描 `source_dir/**/*.md`（跳过 `.obsidian/`、`.trash/`）；
  2. 解析 frontmatter（宽松：无 frontmatter 也能导，标题取 H1 或文件名）；
     生成 id/slug（slugify 拼音，冲突 -2）；`tags` 收进同名合集；
     其余 Obsidian 字段（aliases/date/cssclass）原样保留透传；
  3. 建两级映射：`文件名→slug`，供链接重写；`[[Name]]`→`[[slug]]`、
     `[[Name|alias]]`→`[alias](entries 详情)`（拍板：显示别名、链接 slug）；
  4. 附件：把被引用的图片拷到 `vault/attachments/import-<日期>/`，
     `![[pic.png]]` → `![](attachments/import-.../pic.png)`；
  5. 全部落库 `source="import"`；返回报告 `{imported, links_rewritten,
     attachments, skipped}`。
- `dry_run=true` 只算报告不写（前端先预览再确认执行）。
- 前端：SettingsPage 新「数据导入」区块——路径输入框（MVP 手动粘贴路径，
  **不做** Electron 文件夹选择对话框，避免为此加 IPC）+ 预览/执行两步。
- 幂等性拍板：重复导入不查重，靠 slug 自动 -2 后缀；导入报告里提示用户。

**验收**：一个真实 Obsidian vault 导入后——条目/合集正确、双链可点、
图片可显示、`source=import` 可筛选。测试覆盖：无 frontmatter 文件、
链接重写（含别名）、附件拷贝、dry_run 不落库。

**提交点**：`feat: obsidian vault importer`

## IMP-6 对话内搜索（第二梯队）

**现状**：会话多后无法定位"上次聊过的结论"。`messages` 表无 FTS。

**方案**（MVP 拍板：**当前会话筛选模式**，不做跨会话）：
- ChatPage 头部加搜索输入框（icon Search）；
- 输入关键词 → 消息列表切换为"仅命中"模式（client-side 过滤
  `message.content.includes`，命中词用 `<mark>` 高亮——MarkdownView 需支持
  高亮：渲染前把命中词包 `==word==`？拍板：简单方案——在纯文本层高亮，
  assistant markdown 消息在正文前先做 `content.split(keyword)` 拼接 `<mark>`
  会破坏 markdown；改为**命中消息整条高亮边框 + 计数**，正文内不做词级高亮）；
- 清空恢复完整列表。跨会话搜索列为未来项（需 messages_fts 表，schema v6+）。

**验收**：长会话里搜关键词，只剩命中消息且计数正确；清空恢复。

**提交点**：`feat: in-session message search`

## IMP-7 长对话摘要压缩（第二梯队）

**现状**：`routes/chat.py` 的 `_history_messages` 硬截最近 `HISTORY_ROUNDS=20`
轮，更早内容静默丢失。DESIGN §13 风险表 v0.2 项。

**方案**（增量摘要 + 缓存）：
- schema v6：`conversations` 加 `summary TEXT`、`summarized_until TEXT`
  （已摘要覆盖到的时间戳）；走既有 `_migrate` 链 + 纯加列。
- 新增 `chat/summarizer.py`：`ensure_summary(chat_service, provider, session_id)`——
  user/assistant 轮数 > 30 时，把 `summarized_until` 之前的溢出轮（连同旧摘要）
  发给 LLM 生成 ≤500 字摘要，回写两列；失败**降级为硬截断**（现有行为），
  不阻塞对话。
- `_history_messages` 改为：`[旧轮→已压缩进 summary] + system 级"对话背景"段
  （build_system_prompt 加参数）+ 最近 20 轮原文`。
- 摘要请求用当前会话 provider/model（glm-coding 的 Anthropic 通道同样适用），
  不带工具、不走 RAG。
- 成本拍板：仅超阈值触发、增量合并、会话内缓存（不重复摘要）。

**验收**：FakeProvider 脚本化测试——超 30 轮后触发摘要调用一次、后续轮命中
缓存不再调用、summary 注入 system prompt、provider 失败时降级硬截断且对话正常。

**提交点**：`feat: rolling conversation summary for long chats`

## IMP-8 记忆去重合并 + 向量召回（第二梯队，即 VECTOR_SEARCH_PLAN 阶段 E）

**现状**：`skills/memory.py` 的 save_memory 不查重（靠 LLM 自觉传
`replaces_entry_id`）；`chat/memory.py` 的 recall 纯关键词打分，零词面重合
召回不到。

**方案**（两个独立子项，可分开实施提交）：
1. **保存查重**：`save_memory` 落库前用 `VectorIndex.query(新记忆文本, limit=3)`
   检索「记忆」合集（结果按 entry 的 collections 过滤），cos 相似度 ≥0.80
   视为疑似重复——**不自动合并**，在工具返回里附加
   `{"duplicate_hint": {"entry_id", "title", "similarity"}}`，提示模型
   "若为更新请带 replaces_entry_id 重试"（保守决策：合并与否由模型/用户判断）。
2. **召回增强**：`chat/memory.py` 的 `recall()` 在 vectors 可用时加向量通道——
   `VectorIndex.query(关键词拼接文本)` 后按「记忆」合集过滤取 top3，与现有
   关键词打分结果 RRF 融合（复用 `chat/rag.py` 的融合常数思路）；
   keywords 机制与常驻注入保持不变。
- 测试：FakeEmbedder 语义簇（conftest 已有 `SEMANTIC_CLUSTERS`/
   `vector_storage` fixture）覆盖查重命中/不命中、召回跨词面命中。

**提交点**：`feat: memory dedup hint and vector-assisted recall`

## IMP-9 自动更新（第二梯队）

**现状**：`electron-builder.yml` 的 publish 指向 example.com 占位；无任何
更新检查。

**方案**（拍板：轻量检查档，不引入 electron-updater）：
- 主进程 `main/index.ts` 启动 10s 后（不阻塞首屏）调
  `https://api.github.com/repos/hozin25/Kate-Cortex/releases/latest`，
  比对 `app.getVersion()`；有新版 → `dialog.showMessageBox` 提示 +
  `shell.openExternal` 打开 release 页人工下载安装。
- **国内网络现实**：GitHub API 可能超时——失败静默跳过（每会话最多一次）；
  可加 env `KATE_UPDATE_CHECK=0` 关闭。
- 前置条件：仓库推到 GitHub 且发 release 时把 `Kate-Cortex-Setup-x.y.z.exe`
  传为 release asset；`package.json` 的 version 与 pyproject 同步 bump
  （新增小脚本或手动，拍板手动）。
- electron-updater 全自动档（差量下载+签名校验）列为未来项：需要稳定
  publish 服务与代码签名，当前个人自用不划算。

**验收**：本地把 version 改小 + 伪造一个 latest release 响应（mock 或临时
本地 http）→ 弹更新提示；断网/超时不影响启动。

**提交点**：`feat: lightweight update check against github releases`

## IMP-10 vault 迁移/导入（第二梯队）

**现状**：打包版 vault 在 `%USERPROFILE%\Kate-Cortex\vault`，dev 版在仓库
`vault/`，互为孤岛；无搬家入口。

**方案**（拍板：**合并式知识迁移**，对话历史不迁）：
- 后端 `POST /api/vault/import {source_dir}`（与 IMP-5 共用底座，但源是
  **Kate-Cortex 自己的 vault**，frontmatter 完全兼容无需转换）：
  1. 扫描 `source_dir`（跳过 index.sqlite*/.trash/.obsidian）；
  2. md 拷入当前 vault（同名冲突自动重 slug）；attachments/ 整目录合并拷贝；
  3. `storage.reindex()` 重建索引（含向量 backfill 提示）；
  4. 可选合并 API keys：读源 settings 表解密（DPAPI 同用户可行）→ 本库
     update（只补缺失的 provider，不覆盖已有）。
- 前端：SettingsPage「数据管理」区块（与 IMP-5 的导入入口并排）：
  当前路径展示 + 源路径输入 + 确认弹窗（提示会拷贝不删除源）。
- 安全：dry_run 报告先行；绝不删源目录。

**验收**：从 dev vault 导入打包版（或反向）——条目/合集/双链/附件完整、
key 合并、源目录原样未动。测试覆盖冲突 slug、attachments 合并、dry_run。

**提交点**：`feat: vault import between data directories`

---

## 实施顺序与依赖建议

1. **IMP-1 → IMP-2 → IMP-4 → IMP-3**：第一梯队按此序（3 最重、放最后单独做）。
2. **IMP-5 与 IMP-10 共用导入底座**：先做 5（转换逻辑多），10 顺势复用；
   或先做 10（简单）验证底座再做 5。二选一，拍板倾向先 10 后 5。
3. IMP-6/7/8/9 相互独立，任意顺序；IMP-7 动 schema（v6），收尾注意跑全量
   迁移测试（test_db.py 有 v1→v5 链式用例，需补 v5→v6）。
4. 每项一个独立提交（文案见各节），全部完成后在 IMPLEMENTATION_PLAN.md
   追加阶段 13 记录并在本文档标记状态。

## 统一验收底线

- 后端 pytest 全绿、前端 typecheck/lint/test 全绿；
- 不破坏既有行为：鉴权（新请求走 client.ts）、多模态、记忆、MCP 冒烟
  （`uv run python tests/smoke_mcp_server.py`）不受影响；
- 每项完成同步更新对应文档段落（DESIGN 相关小节 / README 特性列表如涉及）。
