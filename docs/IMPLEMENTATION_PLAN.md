# Kate-Cortex 实施计划

> 可执行计划 · 创建 2026-08-17 · 依据：[REQUIREMENTS](./REQUIREMENTS.md) ·
> [DESIGN v0.2](./DESIGN.md) · [TECH_STACK](./TECH_STACK.md)
>
> 用法：按阶段顺序执行；每个任务有编号、产出、验收标准；每阶段收尾做
> 提交点。总预估 6~7 人天。

---

## 0. 前置事项（开工前，0.25 天内解决）

### 0.1 拍板两项未决问题

| 问题 | 推荐结论 | 理由 |
|---|---|---|
| vault 默认路径 | 开发期 `<repo>/vault/`；打包版 `%USERPROFILE%\Kate-Cortex\vault`；config + settings 可覆盖 | 开发热迭代方便；生产数据不混入代码目录 |
| 项目名 | 维持 Kate-Cortex | 无更名动机 |

### 0.2 环境清单

| 工具 | 版本 | 用途 |
|---|---|---|
| uv | latest | Python 环境与依赖 |
| Python | 3.12+ | 后端 |
| Node.js | 22 LTS | 前端 + Electron |
| pnpm | 9+ | 前端包管理 |

### 0.3 首次提交（当前仓库还是空的）

```bash
git add .gitignore README.md docs/ vault/.gitkeep
git commit -m "docs: project requirements, design and tech stack"
```

---

## 阶段 1：后端知识库骨架（≈1 天）

**目标**：知识库 REST API 全功能可用，中文搜索可用，测试全绿。

| # | 任务 | 产出 | 依赖 |
|---|---|---|---|
| ~~1.1~~ | ✅ 初始化 `backend/` | `pyproject.toml`（fastapi / uvicorn / pydantic / python-frontmatter / jieba / pytest / httpx / pytest-cov），`uv sync` 跑通，src 布局 | — |
| ~~1.2~~ | ✅ `config.py` | vault / db 路径、端口；环境变量覆盖 | 1.1 |
| ~~1.3~~ | ✅ `db.py` | **全量 schema 一次建齐**（entries / tags / entry_tags / entry_links / entries_fts / conversations / messages / settings）+ 简易 migration（schema_version 表） | 1.2 |
| ~~1.4~~ | ✅ `frontmatter.py` + 单测 | 解析 / 生成 / 字段校验 / roundtrip 不丢内容 | 1.1 |
| ~~1.5~~ | ✅ `linking.py` + 单测 | `[[slug]]` 提取（跳过代码块与行内代码） | 1.1 |
| ~~1.6~~ | ✅ `slugify.py` + 单测 | 中文→拼音（pypinyin），异常兜底时间戳，≤60 字符 | 1.1 |
| ~~1.7~~ | ✅ `storage.py` + 单测 | 双写 CRUD、软删/恢复、id/slug 生成（当日序号自增）、`sync()` 差异扫描 | 1.3、1.4、1.6 |
| ~~1.8~~ | ✅ `search.py` + 单测 | jieba 切词、FTS5 索引随写随更、中文查询 | 1.3 |
| ~~1.9~~ | ✅ `routes/` + 集成测试 | entries CRUD / restore / links、tags、sync、health（httpx + 临时目录） | 1.7、1.8 |

**执行记录（2026-08-18 完成阶段 1）**：
- 测试 88 通过，覆盖率 94%（核心模块 ≥84%）
- 偏差 1：`links` 表改为 `entry_links(from_id, to_slug)` 按 slug 存储——否则前向引用
  （链接指向尚未创建的条目）永远无法解析；DESIGN.md §3.3 已同步
- 偏差 2：`uvicorn kate_cortex.main:app` 的模块级 app 通过 conftest `pytest_configure`
  重定向数据目录，避免测试污染 dev vault
- 冒烟脚本：`backend/tests/smoke_stage1.py`（创建→过滤→详情→更新→中文搜索→软删→恢复）

**验收**：
- `uv run pytest --cov` 全绿，核心模块覆盖 ≥ 80%
- curl 冒烟：创建（中文标题）→ 列表过滤 → 详情 → 更新 → 全文搜索中文关键词 →
  软删 → 恢复，全链路通过；vault 里 md 文件与 frontmatter 正确

**提交点**：`feat: backend knowledge base skeleton`

---

## 阶段 2：Provider 层 + 对话模块（≈1.5 天）

**目标**：能和真实模型流式对话（纯文本，暂无工具）；会话历史可查。

| # | 任务 | 产出 | 依赖 |
|---|---|---|---|
| 2.1 | `providers/base.py` + `FakeProvider` | `StreamEvent` 协议（`TextDelta` / `ToolCallDelta` / `Done`）；FakeProvider 支持脚本化回放（测试基石） | 阶段 1 |
| 2.2 | `providers/deepseek.py` / `glm.py` | openai SDK `stream=True`；**流式 tool_calls 增量拼接归一化**（两家格式差异在此吸收） | 2.1 |
| 2.3 | 对话数据层 | `chat/service.py`：会话 CRUD、消息追加、标题自动生成（首条消息前 20 字） | 1.3 |
| 2.4 | `routes/chat.py`（会话部分） | sessions CRUD + 历史消息端点 | 2.3 |
| 2.5 | SSE 对话端点 | `POST /:id/chat` → `citations`(空) → `delta`* → `done`；AbortController 断开即取消任务 | 2.2、2.4 |
| 2.6 | 设置模块 | settings 读写、`PUT /api/settings`、`POST /api/providers/test`（真实连发一条 ping 消息） | 2.2 |

**执行记录（2026-08-18 完成阶段 2）**：
- 测试 123 通过；真实 key 冒烟 DeepSeek + GLM 双 PASS（`tests/smoke_stage2.py`）
- 偏差：provider `chat_stream` 用同步 Iterator + StreamingResponse 线程池
  （而非 AsyncIterator），FakeProvider 回放更简单，DESIGN §5 签名语义不变
- 偏差：缺 API key 在「创建会话」时报 400（fail fast）；`providers/test` 失败返回
  502 JSON `{ok: false}`；GLM 默认模型定为 `glm-4-flash`
- `list_sessions` 排序加 rowid 决胜（微秒时间戳碰撞时偶发乱序）

**验收**：
- FakeProvider 驱动的 SSE 集成测试绿（正常流、中断流、上游报错 502）
- 真实 key 冒烟：DeepSeek、GLM 各完成一轮流式对话，历史落库、重开应用可续

**提交点**：`feat: llm providers and sse chat module`

---

## 阶段 3：收集 skill + RAG（≈1 天）

**目标**：核心闭环跑通——对话中「记一下」入库、AI 主动建议、RAG 引用。

| # | 任务 | 产出 | 依赖 |
|---|---|---|---|
| 3.1 | `chat/prompts.py` | system prompt：人设 / 工具使用规则（何时 save、何时建议）/ RAG 知识段模板 | 2.5 |
| 3.2 | `skills/knowledge.py` | `save_knowledge`（调 storage 双写，source=chat + conversation_id）/ `suggest_save`（仅构造建议数据） | 1.7 |
| 3.3 | agent loop | tool_call 分支：执行工具 → `tool_result` / `suggest` SSE 事件 → 结果回传 LLM 二次生成 → 继续流式；一轮内允许多次工具调用（上限 3 防死循环） | 2.5、3.2 |
| 3.4 | `chat/rag.py` | jieba → FTS5 top3（每条截 ~500 字）→ 注入 system prompt 尾部；`knowledge_refs` 落库；`rag_enabled` 请求级开关 | 1.8、3.1 |
| 3.5 | 集成测试 | FakeProvider 脚本化吐 tool_call → 验证入库产物、SSE 事件序列、二次生成；suggest 流不落库 | 3.3 |

**执行记录（2026-08-18 完成阶段 3，★ M3 最小闭环达成）**：
- 测试 145 通过；真实模型三场景冒烟全 PASS（`tests/smoke_stage3.py`：
  DeepSeek 指令保存 / GLM 主动建议+确认入库 / DeepSeek RAG 引用）
- 偏差：`search.match_expr` 增加中文疑问词/虚词停用词过滤——
  否则「连接池怎么调优」因 AND 上「怎么」而零召回
- agent loop 落库策略：中间轮 tool 消息不落库；最终 assistant 消息带
  `tool_calls`（执行摘要）与 `knowledge_refs`（RAG 命中）；历史回放只带
  user/assistant 文本（工具细节不重复注入）
- FakeProvider 升级支持 `rounds` 多轮脚本（agent 二次生成测试基石）

**验收**（真实模型三场景）：
1. 对话中输入「把刚才这个记一下」→ 保存卡片出现 → vault 生成 md、frontmatter 正确
2. 聊出一个明显结论 → AI 主动弹建议卡片 → 点确认（用 curl 模拟）→ 入库
3. 先存一条知识 → 新会话问相关问题（RAG 开）→ 回答引用该条目

**提交点**：`feat: knowledge capture skill and rag injection`

---

## 阶段 4：前端（≈2 天）

**目标**：dev 模式（终端 A `uv run`、终端 B `pnpm dev`）下完整桌面体验。

| # | 任务 | 产出 | 依赖 |
|---|---|---|---|
| 4.1 | 脚手架 | electron-vite（react-ts）；Tailwind 4 + shadcn/ui init；装 motion / shiki / lucide-react / zustand / react-router / react-hook-form / zod | — |
| 4.2 | 主题系统 | 暗色玻璃拟态 tokens（CSS variables）、`.dark` 明暗切换（默认暗）、基础组件 `GlassPanel` / `GradientText` | 4.1 |
| 4.3 | 布局 + 路由 | 左侧栏（导航：对话/知识库/设置 + 上下文列表容器）、三主区路由 | 4.2 |
| 4.4 | API 层 | `client.ts`（fetch 封装、错误 toast）+ `sse.ts`（ReadableStream 解析、abort） | 4.1 |
| 4.5 | ChatPage | 会话列表（重命名/删除）、消息气泡（流式 markdown + shiki 高亮 + 打字光标）、输入框（Enter 发送 / Shift+Enter 换行）、RagToggle | 4.3、4.4 |
| 4.6 | 收集 UI | `SavedCard`（点击跳详情可改）、`SuggestCard`（确认→`POST /api/entries` / 忽略）、`CitationChips`（跳条目） | 4.5 |
| 4.7 | 知识库页 | LibraryPage（类型/标签过滤 + 搜索 + 卡片列表）、EntryDetailPage（元数据、来源徽标 chat→跳回会话、反向链接）、EntryEditPage（frontmatter 表单 + CodeMirror） | 4.4 |
| 4.8 | SettingsPage | Provider key / 默认模型 / RAG 默认开关 / vault 路径 / 连通测试按钮 | 4.4 |
| 4.9 | Vitest | SuggestCard 确认流、SavedCard 渲染、流式文本追加渲染 | 4.6 |

**执行记录（2026-08-18 完成阶段 4）**：
- 前端 typecheck（node+web）与 ESLint 全绿；Vitest 6 测试通过（SuggestCard 确认/忽略流、
  SavedCard 渲染、流式文本追加）；后端 145 测试通过
- 偏差 1：后端补 CORS 中间件（DESIGN 未提及）——dev 期渲染进程由 vite 提供且端口可能
  被占用顺延（5173→5176），故按正则放行本地任意端口
- 偏差 2：electron-vite 脚手架自带 .gitignore（out/、node_modules/）已覆盖构建产物，
  根 .gitignore 增补的 Tauri 段实为多余但无害，保留
- 人工走查中发现并修复：glm-4-flash 对「记一下」仅口头确认不调工具（tool_calls 为空、
  条目表无记录）→ prompts.py 记忆规则重写：记忆=必须调 save_knowledge 落库 +
  【禁止虚假确认】；真实 GLM 复验通过（citations→tool_result→delta→done）
- 走查进度：对话→保存链路已验证；其余项用户继续验证中

**验收**（dev 模式人工走查 10 项）：新建会话→流式对话→中断→重开续聊→
「记一下」保存卡片→建议卡片确认/忽略→RAG 开关对比→知识库过滤搜索→
编辑条目→设置页测连通。

**提交点**：`feat: desktop ui with dark glassmorphism theme`

---

## 阶段 5：Electron 桥接 + 打包（≈1 天）

**目标**：出可分发的 Windows 安装包。

| # | 任务 | 产出 | 依赖 |
|---|---|---|---|
| 5.1 | `electron/sidecar.ts` | spawn（dev: `uv run`；prod: exe）、health 轮询、就绪信号、退出 SIGTERM→超时强杀、端口占用探测复用 | 阶段 4 |
| 5.2 | `electron/main.ts` | 启动时序（sidecar ready → 创建窗口）、app quit 清理、窗口基础配置（无框/最小尺寸） | 5.1 |
| 5.3 | 打磨 | 快捷键（Ctrl+N 新会话、Ctrl+K 聚焦搜索）、空状态插画、错误 toast、加载骨架 | 5.2 |
| 5.4 | 打包 | PyInstaller spec（onefile，含 jieba 字典资源）→ electron-builder `extraResources` → nsis 安装包 | 5.2 |
| 5.5 | 安装包冒烟 | 干净环境：安装→启动→全流程→退出；任务管理器确认无 Python 残留 | 5.4 |

**提交点**：`feat: electron integration and packaging` → tag `v0.1.0`

---

## 里程碑

| 里程碑 | 时点 | 意义 |
|---|---|---|
| M1 | 阶段 1 末 | 知识库 API 可用（curl 级） |
| M2 | 阶段 2 末 | 真实模型流式对话 |
| **M3** | **阶段 3 末** | **★ 最小闭环：对话→沉淀→引用（无 UI，Swagger 手动玩）** |
| M4 | 阶段 4 末 | 完整桌面体验（dev 模式） |
| M5 | 阶段 5 末 | 可分发安装包 |

---

## 执行规则

1. **测试先行**：单测模块（frontmatter / linking / slugify / search / providers）
   先写测试再实现；API 层用集成测试覆盖。
2. **阶段收尾三件事**：全量测试 → 按验收清单人工冒烟 → git 提交点。
3. **设计变更回写**：实现中发现 DESIGN.md 有出入，先改文档再写码，保持三份文档是事实。
4. **每阶段结束更新本文档**：勾掉完成项，记录偏差（工时超支、方案调整）。

## 风险触发器（停下来找用户讨论，不要自行绕过）

| 触发条件 | 动作 |
|---|---|
| 流式 tool_calls 兼容问题排查超半天 | 停下讨论非流式 fallback（对话体验降级换取稳定） |
| ~~jieba 搜索召回明显差~~ | ✅ 2026-08-18 触发并处置：同义改写零召回（问「身份」条目只有「学生」）。与用户讨论后选 **A. 用户档案常驻注入**（tag=个人信息 无视 RAG 开关注入 system prompt，DESIGN §7 已增补）；向量检索仍留 v0.2 |
| PyInstaller 产物被杀软拦截且无法豁免 | 讨论改 `uv run` 常驻 / 要求装 Python 环境 |
| GLM 与 DeepSeek 工具调用行为差异过大 | 讨论是否 MVP 只保一家、另一家降级纯对话 |
