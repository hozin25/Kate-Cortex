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

## 阶段 6：向量混合检索（≈1.5 天，2026-09-01 完成）

**目标**：RAG 升级为 FTS + 向量双通道混合检索，同义改写可召回；向量索引
可查看状态、可重建。实施清单见 [VECTOR_SEARCH_PLAN.md](./VECTOR_SEARCH_PLAN.md)。

| # | 任务 | 产出 | 依赖 |
|---|---|---|---|
| 6.0 | spike | sqlite-vec 0.1.9 装包验证：Windows + Py3.12 扩展加载、vec0 TEXT 主键 + cosine 建表、KNN/按主键删/全表删/LEFT JOIN 全可用——**无需映射表兜底** | — |
| 6.1 | `providers/embedding.py` | `GLMEmbedder`（批量 64/截 1500 字/1024 维）+ `FakeEmbedder`（语义簇确定性向量，测试桩） | — |
| 6.2 | `db.py` v5 | sqlite-vec 扩展加载（失败降级 `vec_enabled=False`）+ `entries_vec` vec0 表（每次启动幂等建，不进 migration 链） | 6.0 |
| 6.3 | `vectors.py` | `VectorIndex`：index/remove/query/status/clear/rebuild/backfill（幂等可续跑，缺 md 条目计 failed 不中断） | 6.2 |
| 6.4 | `storage.py` 挂钩 | create/update/delete/restore 五条路径挂向量；**事务提交后补嵌**，网络失败不阻断保存；reindex 只清不嵌 | 6.3 |
| 6.5 | `chat/rag.py` | 双通道各取 top6 → RRF（1/(60+rank)）融合取 top3；向量故障当轮退化纯 FTS；签名与 SSE 协议不变 | 6.4 |
| 6.6 | 设置与端点 | settings 加 `embedding_model`；`GET /api/embeddings/status`、`POST /api/embeddings/rebuild`；设置页状态行 + 重建按钮 + 隐私说明 | 6.3 |
| 6.7 | 测试与冒烟 | FakeEmbedder 语义簇验收（「出去玩」零词面召回「感冒保暖」条目）；`tests/smoke_embedding.py`（真实 key 三场景） | 全部 |

**执行记录（2026-09-01 完成阶段 6）**：
- 后端 222 测试通过（+22）；前端 typecheck / ESLint / Vitest 全绿
- 偏差 1：vec0 建表放 `init_schema()` 幂等执行而非 migration 链——扩展可用性
  与 schema 版本正交，避免「迁移到 v5 但扩展缺失」的中间态；v4→v5 无数据搬迁
- 偏差 2：embedder 解析改为「每次调用读 settings」（对齐 ProviderFactory 的
  每请求构建），用户后配 glm key 免重启
- FakeEmbedder 首版在构造函数里有解包 bug（`sorted(dict)` 只返回键），
  被新测试当场抓住——语义簇桩是本次回归防线的关键
- 验收用例：`test_semantic_recall_across_word_gap`（纯 FTS 下必然空手而归的
  查询，经向量通道召回）通过；真实 key 冒烟脚本就绪（`smoke_embedding.py`，
  含 rebuild 端点全量补嵌）

**验收**：
- `uv run pytest` 全绿；配好 glm key 后设置页显示「已索引 x/y」，重建按钮可用
- 真实 key 冒烟：`KATE_GLM_KEY=... uv run python tests/smoke_embedding.py`

**增补执行记录（同日：硅基流动 provider）**：
- 动因：用户智谱标准账户无余额（编程套餐不含 embedding），接免费档
  `BAAI/bge-m3`（原生 1024 维，与 float[1024] 向量表匹配）
- embedding.py 抽出 `_OpenAICompatEmbedder` 基类（client_factory 可注入，
  对齐 chat provider 测试模式）：GLM（批量 64、支持 dimensions）/ 硅基流动
  （批量 32、bge-m3 固定维度不传 dimensions）
- settings 新增 `embedding_provider` / `embedding_api_key`（glm 为空时回退
  provider_keys["glm"]，硅基流动需独立 key）；设置页加服务商切换 + key 输入，
  切换时提示重建（两家属不同向量空间）
- 测试 235 通过（+13：批量切分/dimensions 差异/截断/顺序还原/key 归属回退）；
  冒烟脚本支持 `KATE_SF_KEY=... KATE_EMBEDDING_PROVIDER=siliconflow`

**提交点**：`feat: vector hybrid search with sqlite-vec`

---

## 阶段 7：语义空间三维视图（≈2.5 天，2026-09-01 完成）

**目标**：把向量索引降维成 3D 点云，知识库「立体」tab 可视化语义空间
（旋转/悬停/点击跳转，按合集着色）。实施清单见
[VECTOR_GRAPH_PLAN.md](./VECTOR_GRAPH_PLAN.md)。

| # | 任务 | 产出 | 依赖 |
|---|---|---|---|
| 7.0 | spike | scikit-learn 1.9 装包；`np.frombuffer` 反序列化验证；t-SNE 3D 耗时实测（300 点 0.79s） | — |
| 7.1 | `projection.py` | `ProjectionCache`：L2 归一化 → PCA(50) 预降维 → t-SNE 3D（seed 42 确定性）；签名内存缓存；阈值分派（<3 空态 / <20 PCA 兜底 / >5000 降级 PCA） | 7.0 |
| 7.2 | 端点与装配 | `GET /api/embeddings/projection`、`POST .../refresh`；`app.state.projection` 装配；`ProjectionOut` 模型 | 7.1 |
| 7.3 | 前端 | three + r3f v9 + drei；`VectorGraph`（点云/OrbitControls/tooltip/图例过滤/WebGL 降级）+ `pointColors` 纯函数；LibraryPage 列表/立体双 tab（`?view=graph`） | 7.2 |
| 7.4 | 测试与冒烟 | `test_projection.py`（4 簇 × 12 条簇分离验收 + 缓存签名 + 阈值）；API 用例 4 个；`smoke_projection.py`（临时 vault 播种人工验收） | 全部 |

**执行记录（2026-09-01 完成阶段 7）**：
- 后端 247 测试通过（+12）；前端 typecheck / ESLint / Vitest 全绿（+8：
  pointColors 纯函数）
- **偏差 1（算法）**：计划书原定「t-SNE 直接作用于 1024 维向量」，实测
  小样本下 3D t-SNE 退化为球壳散点（2 簇 24 点簇间/簇内距离比 0.98x）。
  改为 **PCA 预降维到 min(50, n-1) 再 t-SNE** 的标准管线，2 簇修复至
  1.40x、4 簇 48 点 ~1.6x、n=200 耗时 0.65s 且逐位确定；已回填计划书 §2
- **偏差 2（坐标归一）**：计划书原定「逐维 min-max 后等比缩放」，实现改为
  质心居中 + 等比缩放进 [-1,1]（逐维拉伸不保形，等比才保形状）
- 调试发现：FakeEmbedder 的 `_unit_vector` 用 `random.random()`（恒正），
  所有向量落在正象限、两两余弦 ~0.74，与其「跨簇近乎正交」的文档契约不符
  （对检索验收无碍，间隙仍显著）；本项目**未改** FakeEmbedder，靠 PCA 的
  隐式中心化消解，留档备查
- 渲染验收：临时 vault（4 簇 × 10 条）+ 真实后端 + 静态 renderer，浏览器
  人工通过——点云辉光与配色、图例隐藏、tooltip、点击跳转详情、旋转缩放、
  列表 tab 回归
- r3f 的 three.js JSX 属性触发 `react/no-unknown-property`，文件级 eslint
  豁免并注明原因

**验收**：
- `uv run pytest` 全绿；`pnpm typecheck && pnpm test` 全绿
- 人工冒烟：`uv run python tests/smoke_projection.py` 播种临时库 →
  `KATE_VAULT_PATH=... KATE_DB_PATH=... uv run uvicorn kate_cortex.main:app
  --port 1738` → 知识库「立体」tab

**提交点**：`feat: 3d semantic space view with tsne projection`

---

## 阶段 8：多模态图片输入（2026-09-06 完成）

**目标**：对话可直接粘贴/拖入/选择图片提问（报错截图问答），附件本地落盘可追溯。

| # | 任务 | 产出 | 依赖 |
|---|---|---|---|
| 8.1 | `attachments.py` | data URL 落盘 `vault/attachments/YYYY/MM/`（≤4 张/条、各 ≤5MB、png/jpeg/webp/gif）、markdown 引用解析/剥离/读回 | — |
| 8.2 | 多模态消息流 | `ChatRequest.images`；chat 路由落盘+嵌 markdown 引用；历史回放按模型展开为多模态分块（OpenAI image_url），非视觉模型降级「[图片]」占位 | 8.1 |
| 8.3 | Provider 层 | `vision_supported()`（glm-coding 全支持、deepseek 不支持、其余按模型名 v 段判断）；anthropic_compat 把 image_url data URL 转 Anthropic image block | 8.2 |
| 8.4 | 附件静态服务 | `GET /api/attachments/{path}`（resolve 后必须仍在 attachments 目录内，防穿越） | 8.1 |
| 8.5 | 前端 | ChatInput 粘贴/拖拽/选图 + 缩略图（乐观渲染 data URL）；MessageBubble 含图消息走 markdown；MarkdownView 把 attachments/ 引用指向本地后端 | 8.4 |

**执行记录（2026-09-06 完成阶段 8）**：
- 后端 295 测试通过（+19：落盘校验/引用解析/视觉判定/anthropic 转换/多模态
  全链路/静态服务防穿越）；前端 typecheck / ESLint / Vitest（17）全绿
- 偏差：用户主路径是 glm-coding（唯一有余额且 glm-5.3 原生多模态）——
  Anthropic 协议的 image block 转换是该功能的关键路径，配了独立单测
- 决策：图片以 markdown 引用嵌入消息 content（SQLite 零迁移、UI 天然渲染、
  本地可追溯）；RAG 检索与标题生成用剥离图片后的纯文本
- 已知边界：暂无图片压缩（5MB 内原图直发）；历史含图消息在每轮都会重发图片
  token（与主流客户端一致，HISTORY_ROUNDS=20 轮截断兜底）

**提交点**：`feat: multimodal image input for chat`

---

## 阶段 9：记忆管理页（2026-09-06 完成）

**目标**：对标 ChatGPT Memory 的管理入口——事后集中查看/编辑/删除全部自动记忆，
不再只能靠对话中的撤销卡片或翻 Library。

**执行记录**：
- 纯前端工作，**后端零改动**：复用 `GET /entries?collection=记忆`（summary 已含
  keywords/importance）、`PUT /entries/:id`（keywords/importance 可编辑）、
  `DELETE /entries/:id`（软删）
- 新增 `MemoriesPage`：与常驻注入同序（importance, created_at 降序）排列、
  关键词 chips + 重要度星标、点击展开内容（按需拉详情，避免 N+1）、行内编辑
  （标题/内容/场景关键词/重要度）、确认删除（提示 .trash 保留）、标题/关键词搜索、
  空状态引导；侧边栏新增「记忆」导航
- `EntrySummary` 前端类型补齐 keywords/importance（后端早已返回）
- Vitest 5 用例（排序/空态/搜索/编辑保存/删除）；typecheck / ESLint 全绿
- 已知取舍：关键词输入为逗号分隔文本（不做逐 chip 编辑），个人规模够用
- 增补（同日）：系统合集防护——「记忆」「个人信息」的删除/重命名在 storage 层抛
  `ProtectedCollection` → API 409（创建不受限，save_memory 依赖自动建合集）；
  前端复用既有错误 toast 零改动。测试 300 通过（+5）。动因：合集级删除会让
  记忆/档案机制对存量条目静默失效（条目还在但按合集名过滤全查不到）

**提交点**：`feat: memory management page`

---

## 阶段 10：对话管理基本操作（2026-09-06 完成）

**目标**：对话消息可管理——重新生成最后回复、编辑用户消息并重发（截断后续）、
删除单条消息、复制消息。

**执行记录**：
- 后端：ChatService 增消息级操作（get/update/delete + `delete_messages_after`
  按 (created_at, rowid) 与 list 同序截断）；chat 路由抽出 `_stream_response`
  共用 SSE 生成器（chat/regenerate/resend 三入口同一条 RAG→citations→agent
  链路）；新增 `POST /:id/regenerate`、`POST /:id/messages/:mid/resend`
  （keep_images 保留原图片引用）、`DELETE /:id/messages/:mid`（会话归属校验）
- 前端：store 抽 `runStream` 复用并新增 regenerate/editMessage/deleteMessage
  （乐观截断/更新，done 后整表刷新校正）；气泡悬停操作栏（复制/编辑/删除，
  最后一条 AI 回复另有重新生成）；用户消息内联编辑器（Ctrl+Enter 重发、
  Esc 取消，编辑框剥离图片引用、重发时后端保留）
- 测试：后端 308（+8：重生成替换旧回复/仅去尾回复/无消息 404/编辑重发
  截断/拒编 assistant/404/删除/跨会话 404）；前端 25（+3）
- 插曲：跑测试时发现 C 盘满（剩 0.3GB）导致临时文件写入失败，清理本会话
  产生的 pytest/kate 临时目录后恢复（仅释放 0.7GB，深层清理待用户决定）

**提交点**：`feat: chat message management (regenerate, edit-resend, delete)`

---

## 阶段 11：MCP 服务端（2026-09-07 完成）

**目标**：兑现 README「桌面端 + MCP 双形态」的服务端侧——外部编码 agent
（Claude Code / Cursor）经 stdio 检索与沉淀用户的知识库和记忆。与阶段
（mcp_client，Kate 用别人的工具）方向相反：别人用你的数据。

| # | 任务 | 产出 |
|---|---|---|
| 11.1 | embedder 工厂共享化 | `make_embedder_factory` 从 main.py 移入 providers/embedding.py（main 模块级会启动 FastAPI 应用，MCP server 不能 import 它） |
| 11.2 | `mcp_server.py` | mcp SDK 2.x `MCPServer` + stdio；6 工具：search_knowledge（复用 rag.retrieve 混合检索）/ get_entry（含反向链接）/ save_knowledge（source=import）/ list_collections / recall_memory / save_memory（含 replaces 覆盖更新）；instructions 指导 agent 何时调用 |
| 11.3 | 入口 | `[project.scripts] kate-cortex-mcp` → `uv run kate-cortex-mcp`；与 1738 HTTP 服务并存（SQLite WAL 多进程读写） |
| 11.4 | 测试与冒烟 | 工具纯函数单测 + 注册验证（319 过，+11）；`smoke_mcp_server.py` 真实 stdio 握手（子进程 → initialize → list_tools → search/save 调用 → 落盘校验）全通过 |

**设计约束**：只增不改（不暴露 update/delete 工具，与记忆 append-only 同原则）；
外部写入一律 `source=import` 打标；stdio 本地进程，不占端口不出网。

**Claude Code 接入**：
`claude mcp add kate-cortex -s user -- uv run --project D:\workspace\Kate-Cortex\backend python -m kate_cortex.mcp_server`

**踩坑**：mcp 2.x 相对 1.x 改名三处——FastMCP→MCPServer（mcp.server.mcpserver）、
`serverInfo`→`server_info`、`isError`→`is_error`；PowerShell Set-Content 默认
编码会损坏 UTF-8 中文源文件（冒烟脚本被写坏一次，重写规避）。

**提交点**：`feat: mcp server exposing knowledge base and memory to coding agents`

---

## 阶段 12：P0 加固四件套（2026-09-07 完成）

**目标**：竞品分析 P0 清单中除打包外的四项一次清完。

| # | 项 | 实现 |
|---|---|---|
| 12.1 | 凭据静态加密 | `security.py`：ctypes 直调 DPAPI（零新依赖），`dpapi:` 前缀 + base64 密文；SettingsService 写侧加密读侧解密（调用方无感）；启动迁移 `encrypt_existing_secrets()` 重写历史明文；非 Windows 恒等降级 |
| 12.2 | 本地 API 鉴权 | `KATE_API_TOKEN` 环境变量启用中间件：X-Kate-Token / Bearer / `?api_token=`（img 场景）三通道，`/api/health` 豁免（sidecar 探测）；未设置不启用，dev 工作流不变。前端 client/sse/MarkdownView 预留 `window.__KATE_API_TOKEN__` 注入（阶段 5 sidecar 落地时接线） |
| 12.3 | vault_path 诚实化 | `SettingsUpdate` 去字段 + `extra=forbid`（发它即 422 明拒）；GET 返回 config 实际生效路径；遗留存储行不再透出；设置页文案改为「启动时确定」 |
| 12.4 | 回收站补全 | `GET /api/trash`（list_trash 按 mtime 倒序）+ `DELETE /api/trash/:id`（彻底删除）+ `cleanup_trash()`（30 天超期启动清理，DESIGN §9 兑现）；前端 TrashPage（恢复/彻底删除/空态）+ 知识库页入口 |

**执行记录**：后端 342 测试通过（+23）；前端 typecheck/ESLint/Vitest（25）全绿。
security.py 首版有 ctypes 函数取用 bug（getter 当函数调），被全量测试当场抓住。

**提交点**：`feat: p0 hardening (dpapi secrets, local api auth, trash ui, honest vault path)`

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
