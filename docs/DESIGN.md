# Kate-Cortex 设计文档

> 个人知识库 + AI 对话桌面应用。本地优先，对话即沉淀。
>
> 版本：v0.2 · 更新：2026-08-17 · 状态：设计阶段（已按新需求重写）
>
> 配套文档：[REQUIREMENTS.md](./REQUIREMENTS.md)（需求）· [TECH_STACK.md](./TECH_STACK.md)（选型）
>
> v0.2 变更：编程知识库 → 通用知识库；AI 对话升级为 MVP 核心；
> 桌面壳 Tauri → **Electron**；新增对话模块、知识收集 skill、RAG 检索设计。

---

## 1. 产品定位

见 [REQUIREMENTS.md](./REQUIREMENTS.md)。一句话：**你和 AI 聊天，聊出价值就沉淀，
下次聊天 AI 引用你的沉淀**。核心闭环：对话 → 沉淀 → 引用 → 越来越懂你。

本文档只讲"怎么实现"。

---

## 2. 架构设计

### 2.1 总体架构

```
┌───────────────────────────────────────────────────────────────┐
│  Electron 壳 (Node.js 主进程)                                  │
│   ├─ Python sidecar 生命周期管理（spawn / 健康检查 / 退出清理）│
│   └─ BrowserWindow → React 前端                                │
├───────────────────────────────────────────────────────────────┤
│  FastAPI 本地服务 (127.0.0.1:1738)                             │
│   ├─ /api/entries   知识库 CRUD                                │
│   ├─ /api/collections 合集                                      │
│   ├─ /api/chat/*    会话 + SSE 流式对话                        │
│   ├─ /api/settings  Provider / API key / RAG 开关              │
│   └─ /api/sync      重新索引                                   │
├───────────────────────────────────────────────────────────────┤
│  业务层 (Python)                                               │
│   ├─ storage.py     markdown ↔ SQLite 双写                     │
│   ├─ search.py      FTS5 + jieba 中文检索                      │
│   ├─ chat/          对话服务（agent loop）+ RAG 注入           │
│   ├─ skills/        save_knowledge / suggest_save 工具         │
│   └─ providers/     LLM 抽象（DeepSeek / GLM，openai SDK）     │
├───────────────────────────────────────────────────────────────┤
│  存储层                                                        │
│   ├─ vault/         markdown 知识文件（按年月归档）            │
│   ├─ index.sqlite   条目/合集/链接/FTS 索引 + 对话历史          │
│   └─ .trash/        软删除区                                   │
└───────────────────────────────────────────────────────────────┘
```

### 2.2 进程模型

```
Electron 主进程 (TypeScript)
  │
  ├─ app 启动 → spawn Python sidecar
  │     开发: uv run uvicorn kate_cortex.main:app --port 1738
  │     生产: resources/kate-cortex-server.exe (PyInstaller onefile)
  │     轮询 GET /api/health，就绪后创建窗口
  │
  ├─ BrowserWindow
  │     dev:  http://localhost:5173   (Vite dev server)
  │     prod: loadFile(本地打包产物)
  │     业务请求全部 → http://127.0.0.1:1738
  │
  └─ app 退出 → kill sidecar（先 SIGTERM，超时强杀）
```

- 脚手架：**electron-vite**（Vite + Electron + TS 一体）
- 开发期**不打包** Python（`uv run` 直跑）；打包放最后阶段（见 TECH_STACK.md §5）
- sidecar 端口被占用（如上次未退干净）：先探测 `/api/health` 是否为本应用（响应带
  app 标识），是则复用，否则换端口重试

### 2.3 一次对话请求的数据流

```
用户输入 → POST /api/chat/sessions/:id/chat
                    │
                    ▼
        chat/service.py  agent loop
                    │
     ┌──────────────┼────────────────────────┐
     ▼              ▼                        ▼
  rag.py 检索    拼 system prompt        providers/ 调 LLM
  (FTS5 top3)    (人设+知识+工具说明)      (openai SDK, stream)
     │                                          │
     │                              ┌───────────┴───────────┐
     │                              ▼                       ▼
     │                        纯文本流                 tool_call
     │                        SSE: delta            save_knowledge /
     │                              │               suggest_save
     │                              │                       │
     │                              │              skills/ 执行入库
     │                              │              (或仅生成建议卡片)
     │                              │                       │
     │                              ▼                       ▼
     │                        SSE: done          SSE: tool_result / suggest
     │                                                  结果回传 LLM 二次生成
     ▼                                                  最终回复继续流式
messages 落库（含 knowledge_refs / tool_calls）
```

---

## 3. 数据模型

### 3.1 知识文件组织（沿用）

```
vault/
├── 2026/
│   └── 08/
│       ├── 20260817-001-redis-pipeline-bug.md
│       └── 20260817-002-fastapi-middleware-design.md
├── .trash/              # 软删除
└── attachments/         # v0.2
```

文件命名 `YYYYMMDD-NNN-slug.md`；中文标题 → slug 用拼音转换或时间戳兜底，标题保留中文。

### 3.2 知识文件格式

```markdown
---
id: kc_20260817_001
slug: redis-pipeline-bug
title: Redis pipeline 在事务模式下不返回结果
collections: [编程]
language: python
source: chat
conversation: kc_conv_a1b2c3
created_at: 2026-08-17T10:30:00+08:00
updated_at: 2026-08-17T10:30:00+08:00
---

正文 markdown，支持代码块、[[slug]] 双向链接。
```

| 字段 | 说明（相对 v0.1 的变化） |
|---|---|
| `type` | **已移除**（v2 起无固定分类，旧文件中的 type 字段解析时忽略） |
| `tags` | **已移除**（v3 起合集为唯一组织机制）。旧文件中的 tags 解析时原样保留在 md 中（透传，不再读写/索引/展示）；「个人信息」tag 由启动迁移转入合集 |
| `collections` | 可选。所属合集名列表（多对多），与索引库双写 |
| `language` | 降为可选元数据（不再绑定独立类型） |
| `source` | **改为** `manual` / `chat` / `import` |
| `conversation` | **新增**，可选。对话沉淀时记录来源会话，详情页可跳回 |

### 3.3 SQLite Schema

```sql
-- ── 知识库（v3：移除 tags 两表，合集为唯一组织机制）──
CREATE TABLE entries (
  id              TEXT PRIMARY KEY,     -- kc_YYYYMMDD_NNN
  slug            TEXT UNIQUE NOT NULL,
  title           TEXT NOT NULL,
  project         TEXT,
  language        TEXT,
  source          TEXT NOT NULL CHECK (source IN ('manual','chat','import')),
  conversation_id TEXT,                 -- 对话沉淀时记录
  file_path       TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE INDEX idx_entries_created ON entries(created_at DESC);
CREATE INDEX idx_entries_conv    ON entries(conversation_id);

CREATE TABLE collections (          -- 用户自建合集；空合集合法，不做孤儿清理
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE entry_collections (
  entry_id      TEXT NOT NULL,
  collection_id INTEGER NOT NULL,
  PRIMARY KEY (entry_id, collection_id),
  FOREIGN KEY (entry_id)      REFERENCES entries(id)     ON DELETE CASCADE,
  FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE
);

CREATE TABLE entry_links (
  from_id  TEXT NOT NULL,
  to_slug  TEXT NOT NULL,          -- 按 slug 存储而非 id：前向引用（目标未建）也能记录
  PRIMARY KEY (from_id, to_slug),
  FOREIGN KEY (from_id) REFERENCES entries(id) ON DELETE CASCADE
);
-- 反向链接查询：entry_links JOIN entries tgt ON tgt.slug = to_slug JOIN entries e ON e.id = from_id

-- ── 中文全文检索：FTS5 + jieba 预分词 ──
-- 写入时 title/content 经 jieba 切词、空格连接后存入 *_tokens 列；
-- 查询时对关键词同样切词后 MATCH
CREATE VIRTUAL TABLE entries_fts USING fts5(
  title_tokens,
  content_tokens,
  entry_id UNINDEXED
);

-- ── 向量检索（v5，§7.2）：vec0 虚表；sqlite-vec 扩展加载失败时此表缺席，
-- 系统降级为纯 FTS，不阻塞启动 ──
CREATE VIRTUAL TABLE entries_vec USING vec0(
  entry_id TEXT PRIMARY KEY,
  embedding float[1024] distance_metric=cosine
);

-- ── 对话（新增）──
CREATE TABLE conversations (
  id          TEXT PRIMARY KEY,         -- kc_conv_xxx (uuid)
  title       TEXT,                     -- 首条消息后自动生成，可改名
  provider    TEXT NOT NULL,            -- deepseek / glm
  model       TEXT NOT NULL,            -- deepseek-chat / glm-4.x
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
CREATE INDEX idx_conversations_updated ON conversations(updated_at DESC);

CREATE TABLE messages (
  id              TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  role            TEXT NOT NULL CHECK (role IN ('user','assistant','tool')),
  content         TEXT NOT NULL,        -- markdown 正文
  tool_calls      TEXT,                 -- JSON：assistant 发起的工具调用
  knowledge_refs  TEXT,                 -- JSON：RAG 引用的 entry id 数组
  created_at      TEXT NOT NULL,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX idx_messages_conv ON messages(conversation_id, created_at);

-- ── 设置（新增；API key 不入 vault，仅存于此 + 本地配置文件）──
CREATE TABLE settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL                   -- JSON
);

-- v0.2 预留：sqlite-vec 向量表
```

### 3.4 一致性策略（沿用）

**markdown 是事实来源，SQLite 是索引**：启动 `sync()` 校验差异告警；写操作先写 md
再写 SQLite，md 失败回滚；手动改文件后用户点"重新索引"。

对话数据（conversations/messages）只存 SQLite，无 md 对应物——它是会话日志而非知识资产；
后续如需导出走 v0.2。

### 3.5 v3 迁移（2026-08-19：删除标签，合集成为唯一组织机制）

- **schema v2 → v3**（`db.py _migrate`）：DROP `tags` / `entry_tags`；`entries_fts`
  去掉 `tag_tokens` 列（FTS5 虚表无法改列，整表重建），迁移当日启动时从 md 真相源
  全量 `reindex()` 重灌（`Database.migrated_from` 门控，仅迁移发生时执行一次）
- **存量数据迁移**（`storage.migrate_profile_to_collection()`，每次启动幂等执行）：
  frontmatter `tags` 含 `个人信息` 的条目 → 收进 `个人信息` 合集并从 tags 移除该项；
  时间戳不变；其余条目的 tags 原样保留在 md 中（frontmatter 层透传，系统不再
  读写/索引/展示）
- **档案注入识别**：`tag=个人信息` → `个人信息` 合集（见 §7）

---

## 4. API 设计

### 4.1 端点总览

```
# 知识库
POST   /api/entries                     创建
GET    /api/entries                     ?collection=&q=&limit=&offset=
GET    /api/entries/:id
PUT    /api/entries/:id
DELETE /api/entries/:id                 软删除
POST   /api/entries/:id/restore         从 .trash 恢复
GET    /api/entries/:id/links           反向链接

# 合集（用户自建，多对多收录条目，唯一组织机制）
GET    /api/collections                 [{name, count}]
POST   /api/collections                 {name}，重名 409
PUT    /api/collections/:name           {name} 重命名（重写成员 frontmatter）
DELETE /api/collections/:name           删除合集，成员条目保留
# ↑ 「记忆」「个人信息」为系统合集（自动记忆/档案注入的识别标志），
#   删除与重命名均 409 拒绝，防止对应机制对存量条目静默失效；创建不受限

# 对话
POST   /api/chat/sessions               {provider, model, title?}
GET    /api/chat/sessions               列表（含最近消息预览）
PATCH  /api/chat/sessions/:id           重命名 {title} / 切换模型 {provider?, model?}
                                         （切 provider 按 DEFAULT_MODELS 解析默认模型，
                                         未配 key 400；只影响之后请求，历史连续）
DELETE /api/chat/sessions/:id
GET    /api/chat/sessions/:id/messages  历史
POST   /api/chat/sessions/:id/chat      发消息 → SSE 流式响应

# 对话内模型切换（2026-09-07 增补）
GET    /api/models                      模型目录：各 provider 的可选模型
                                         （MODEL_CATALOG，free 标注免费档）+ has_key
                                         + vision（vision_supported 现算，与发图拦截
                                         同源），供 ModelPicker 弹层与输入框图片门控

# 对话管理（2026-09-06 增补）
POST   /api/chat/sessions/:id/regenerate                    重新生成：删最后
                                                             条用户消息后的回复并重流（不重复落用户消息）
POST   /api/chat/sessions/:id/messages/:mid/resend          编辑用户消息并重发：
                                                             {content, keep_images=true} 原地更新+截断其后+重流
DELETE /api/chat/sessions/:id/messages/:mid                 删除单条消息（校验会话归属）

# 设置
GET    /api/settings
PUT    /api/settings                    provider keys / 默认模型 / RAG 默认 / vault 路径 / export_dir
POST   /api/providers/test              {provider} 连通性测试

# MCP 服务（多服务接入，2026-09-11 增补；状态缓存供设置页展示可用/不可用）
GET    /api/mcp/servers                 列表（含最近一次实测状态 {ok, message, tool_count, checked_at}）
POST   /api/mcp/servers                 {name, url} 添加：先真实 list_tools 验证，失败 400 不落配置
PATCH  /api/mcp/servers/:id             {enabled} 启用/停用
DELETE /api/mcp/servers/:id             移除
POST   /api/mcp/servers/:id/test        连通性实测（list_tools）并刷新状态缓存

# 系统
POST   /api/sync                        重新索引（FTS 重灌；向量只清不嵌）
GET    /api/health                      {app: "kate-cortex", version}

# 向量索引（v5，§7.2）
GET    /api/embeddings/status           {available, indexed, total}
POST   /api/embeddings/rebuild          清空向量表 + 全量重嵌

# 附件（多模态输入，2026-09-06 增补）
GET    /api/attachments/{rel_path}      图片静态服务（vault/attachments 下，防目录穿越）
```

### 4.2 SSE 事件协议（`POST /api/chat/sessions/:id/chat`）

请求：`{"content": "用户消息", "images": ["data:image/png;base64,…"], "rag_enabled": true}`，
响应 `text/event-stream`。**多模态**（2026-09-06 增补）：`images` 可选（≤4 张，各 ≤5MB，
png/jpeg/webp/gif），落盘 `vault/attachments/YYYY/MM/`，消息 content 以 markdown 图片
引用携带（本地可追溯）；视觉模型（glm-coding 的 glm-5.3 原生多模态；glm 经典端点
按模型名 glm-4v/glm-4.5v 判断）下发时展开为多模态分块（OpenAI image_url /
Anthropic image block，由 anthropic_compat 归一化），文本模型发图 400 引导切换，
历史回放时非视觉模型降级为「[图片]」占位：

| event | data | 说明 |
|---|---|---|
| `citations` | `{entries: [{id, title, slug}]}` | 消息开始，RAG 命中的条目 |
| `delta` | `{text}` | 流式文本片段 |
| `tool_result` | `{entry_id, title, collections}` | save_knowledge 已入库 → 前端渲染保存卡片 |
| `suggest` | `{title, collections, preview}` | AI 建议卡片（**未入库**，等用户确认；合集建议可改可拒） |
| `memory_saved` | `{entry_id, slug, title, keywords, replaced}` | save_memory 已自动记住/更新 → 前端渲染记忆卡片（可撤销） |
| `memory_refs` | `{query, memories: [{entry_id, title, content, keywords, created_at}]}` | recall_memory 命中相关记忆 → 前端渲染「想起」chips；无命中不推 |
| `mcp_notice` | `{message}` | 已接入的 MCP 服务连接失败 → 前端 toast 警告，本次对话降级为无该服务的工具继续 |
| `mcp_changed` | `{ok, message, id?, tools?}` | 会话内 install_mcp / remove_mcp 执行结果 → 前端 toast 成功/警告；配置已持久化，设置页状态同步 |
| `file_saved` | `{title, file_path}` | export_markdown 已落盘独立 .md 文件 → 前端 toast 显示保存路径 |
| `done` | `{message_id}` | 消息落库完成 |
| `error` | `{message}` | 出错 |

用户确认建议卡片 → 前端自行调 `POST /api/entries`（`source=chat` + `conversation_id`）。
中断：前端 `AbortController` 断开 → 后端 asyncio task 取消，未 `done` 的消息不落库。

### 4.3 错误码

`400` 参数缺失/格式错 · `404` 不存在 · `409` slug 冲突 · `502` LLM 上游错误 · `500` 本地异常

---

## 5. LLM Provider 层

```
providers/
  base.py         # Provider 抽象：chat_stream(messages, tools) -> AsyncIterator[StreamEvent]
  openai_compat.py # 公共实现；_request_kwargs() 钩子供子类注入私有参数
  deepseek.py     # base_url = https://api.deepseek.com/v1（付费）
  glm.py          # base_url = https://open.bigmodel.cn/api/paas/v4，免费档 glm-4.7-flash
  glm_coding.py   # Anthropic 协议端点（编程套餐）
  siliconflow.py  # base_url = https://api.siliconflow.cn/v1，免费档 Qwen/Qwen3-8B；
                  #   混合推理 Qwen3 显式 enable_thinking=False，防思考文本污染流
  modelscope.py   # base_url = https://api-inference.modelscope.cn/v1，每日 2000 次免费
```

- 统一用 **openai SDK**，`OpenAI(base_url=..., api_key=...)` 切换各家
- `StreamEvent` 归一化两类事件：`TextDelta` / `ToolCallDelta`——**屏蔽各家在流式
  tool_calls 增量拼接上的格式差异**（这是已知的实现坑，Provider 层集中处理并配集成测试）
- API key 从 settings 读取；缺 key 时创建会话即报错（fail fast）
- embedding（v0.2）：GLM embedding-3 或硅基流动，接口在 base.py 预留
- **免费组合**（2026-09-06 接入，真 API 冒烟通过）：对话 glm-4.7-flash（智谱完全
  免费，30B MoE / 200K 上下文 / 原生 function calling）或 Qwen/Qwen3-8B（硅基流动
  免费档）；更重的任务走魔搭 Qwen3-235B-A22B-Instruct-2507（每日 2000 次免费）；
  向量检索硅基流动 bge-m3（免费）。默认 provider 全新安装指向 glm 免费档

---

## 6. 知识收集 skill

### 6.1 工具定义（OpenAI function calling）

**save_knowledge**（用户指令触发，直接入库）：

```json
{
  "name": "save_knowledge",
  "description": "总结当前对话中的有价值内容并存入知识库。当用户明确要求记下、保存、沉淀某段讨论时调用。",
  "parameters": {
    "title": "知识标题（简洁，可中文）",
    "collections": ["可选。建议收录的合集，只能从系统提示列出的已有合集中选择"],
    "content_markdown": "总结后的正文。聚焦当前讨论主题，保留结论/方法/代码，剔除寒暄与过程。"
  }
}
```

**suggest_save**（AI 主动触发，仅生成建议）：

参数同上。description：*"当对话中出现值得长期保留的结论、方法或决策（即使用户没要求），
调用此工具生成保存建议，交由用户确认。不要在用户没确认前真正保存。"*

**export_markdown**（2026-09-03 增补，交付独立文档文件）：

参数：`title`（同时用作文件名）、`content_markdown`（完整文档）。把内容写成
**不含 frontmatter 的独立 .md 文件**，存入导出文件夹（settings `export_dir`，默认
`文档\Kate-Cortex 导出`，在 vault **之外**——vault 是 `rglob("*.md")` 递归索引的，
放里面会被误收录）。与 save_knowledge 的分工：知识资产入库 → save_knowledge；
交付独立文件（旅游行程 / 报告）→ export_markdown。文件名清洗 Windows 非法字符，
重名自动追加 ` (2)`。SSE 推 `file_saved`，前端 toast 显示路径。

### 6.2 执行流程（agent loop）

```
1. 用户消息进入 loop，LLM 流式生成
2. 若产生 tool_call:
   ├─ save_knowledge  → slug 生成 → md/SQLite 双写（source=chat, conversation_id）
   │                     SSE 推 tool_result（保存卡片）→ 工具结果回传 LLM → 二次生成回复
   └─ suggest_save    → 不写库，SSE 推 suggest（建议卡片）
   │                     工具结果回传 LLM："已展示建议，等待用户确认" → LLM 继续回复
3. 纯文本 → SSE delta 流式 → done 落库
```

**话题边界**（总结范围的界定）：MVP 依赖 LLM 在 system prompt 指导下自行界定"当前
讨论主题"，上下文默认携带最近 20 轮；不做复杂的切分算法。

**system prompt 骨架**（`chat/prompts.py`）：

```
你是 Kate，用户的个人知识助手。
[人设与回答风格]
[工具使用规则：用户说"记一下"等 → 立即 save_knowledge；
 发现高价值结论/方法/决策 → suggest_save 建议，不擅自保存]
[用户档案（常驻注入）：「个人信息」合集的条目；回答与用户本人相关的问题直接采用]
[RAG 知识（可选注入）：以下来自用户知识库，回答可参考并注明来源条目标题]
```

### 6.3 外部工具接入（MCP client，2026-09-02 增补；多服务改造 2026-09-11）

通过 **MCP Streamable HTTP** 让 agent 调用外部工具服务（典型：高德地图 MCP Server，
获得 POI 搜索 / 景点详情 / 路线规划 / 天气查询，支撑旅游行程规划等实时数据场景）。

- **配置**：settings 表 `mcp_servers` 列表（`{id, name, url, enabled}`，最多 10 个；
  旧版单端点 `mcp_url` 启动时自动迁移，见 `SettingsService.migrate_mcp_url`）。
  url 为完整 Streamable HTTP 端点（key 直接拼在 URL 上，如
  `https://mcp.amap.com/mcp?key=…`）。管理入口有三处，全部走同一套校验与状态缓存：
  设置页手动 CRUD（`/api/mcp/servers`）、对话内 `install_mcp` / `remove_mcp` 工具、
  连通性实测（`POST /api/mcp/servers/:id/test`）。添加必须先真实 `list_tools`
  验证通过才落盘，保证设置里的服务都是验证过的
- **会话内安装**：用户把端点发给 Kate（「帮我接入高德地图 MCP，url 是 …」），
  模型调 `install_mcp(name, url)` → 验证 + 落盘 + 推 `mcp_changed` SSE（前端 toast）；
  失败时把原因回传模型如实转告，不落任何配置。安装成功的服务工具表**当轮即刷新**
  （agent loop 每轮从 `McpContext.tool_defs()` 现取），模型下一轮就能调用
- **客户端**（`mcp_client.py`）：官方 mcp SDK（v2）+ Streamable HTTP 传输，对同步
  agent loop 暴露两个同步接口（内部 `asyncio.run`，每次调用独立连接）：
  `list_mcp_tools(url)`（`list_tools` → 转 OpenAI function-calling 工具表）、
  `call_mcp_tool(url, name, args)`（`call_tool` → 结果文本原样回传模型）；
  另含命名空间转换 `to_namespaced_tools` / 反解 `parse_mcp_tool_name`
- **命名空间**：多服务接入下工具名统一加前缀 `mcp__<服务id>__<工具名>`
  （id 为 [a-z0-9_-] 短标识，不含 `__`，可无损反解），避免不同服务的工具重名，
  模型也能从工具名识别所属服务；dispatch 在 `McpContext.dispatch` 完成反解与转发
- **agent loop 融合**：各启用服务的命名空间工具并入 tools 表尾部；`mcp__` 前缀的
  tool_call 反解后转发对应服务。工具结果是纯文本 → 不产生独立 SSE 事件，直接作为
  tool 消息回传；`tool_calls` 照常落库。`MAX_TOOL_ROUNDS` 3 → 8（行程规划需反复
  搜索 + 路线规划）
- **降级与状态**：每轮对话开始时逐服务拉一次工具清单（`McpContext.load`），失败的
  服务合并推一条 `mcp_notice` 后正常继续——只是没有该服务的实时数据，不阻断对话；
  成败都写入状态缓存（`mcp_registry._STATUS`），设置页展示「可用 / 不可用 + 工具数
  + 检测时间」，进设置页时会重新实测一遍
- **提示词**：「接入 / 移除外部工具服务」规则常驻（端点只能来自用户或官方文档、
  严禁编造）；`mcp_enabled`（有服务工具可用）时额外注入「外部实时工具」规则
  （实时信息必须查工具、行程按天分节 Markdown 输出、注明数据来源、失败如实告知）
- 现实约束：携程 / 美团 / 马蜂窝无公开 API；地图类（高德 / 百度 / 腾讯）有官方
  MCP，个人开发者免费额度即可用

---

## 7. RAG 检索

- 触发：`rag_enabled=true`（全局默认开，会话内可切）时，每条用户消息发送前检索
- 检索：消息 jieba 分词 → `entries_fts` MATCH → top 3，每条截取前 ~500 字，
  总预算 ≤ 2000 tokens
- 注入：作为 system prompt 尾部知识段；`messages.knowledge_refs` 记录命中 id，
  前端渲染引用 chips（点击跳条目详情）
- **用户档案常驻注入**（2026-08-18 增补，2026-08-19 v3 改为合集识别）：收录于
  `个人信息` **合集**的条目（按创建时间取前 3 条）**无论 RAG 开关**都注入
  system prompt（位于 RAG 知识段之前）。
  动机：FTS5 是词元精确匹配，无法跨同义改写召回（问「我的身份」但条目里只有
  「学生/教育背景」），而用户画像类问题（我是谁/做什么的）是高频刚需，靠常驻
  注入兜底；档案条目不计入 `citations` / `knowledge_refs`
- v0.2：sqlite-vec 向量召回 + 关键词混合（解决其余同义改写场景）

### 7.1 自动记忆机制（2026-08-31 增补，schema v4）

对话即记忆：Kate 在对话中**自动**记住关于用户本人的耐久事实（健康状况、行程
计划、稳定偏好、重要生活事件、进行中的事），并在后续对话中自然想起——
「昨天问感冒药，今天问出去玩」时主动提醒保暖。对标 ChatGPT Memory 的
「自动保存 + 轻提示 + 事后管理」交互，借鉴 Mem0 的 append-only 原则。

**存储**：记忆 = 知识库 `记忆` **合集**中的普通条目（source=chat，
携带 conversation_id），复用 md/SQLite 双写、回收站、Library 管理全链路。
schema v4 为 entries 增加 `keywords`（JSON 数组，场景触发词）与
`importance`（1-5）两个可空列，frontmatter 同步读写，非记忆条目不受影响。

**工具**（`skills/memory.py`，agent loop 内自动调用）：

- `save_memory`：LLM 判断出现耐久个人事实即调用（无需用户要求）；一条记忆
  只记一个原子事实，**必须**附 3-8 个场景关键词（记感冒时写：感冒/健康/
  保暖/出行/天气）；旧记忆过时（感冒好了）传 `replaces_entry_id` 显式
  覆盖更新，而非模型擅自改写或重复新建
- `recall_memory`：回答与个人生活相关的问题前调用，keywords 由模型从当前
  话题提炼并联想相关场景（问「出去玩」可查：出行/健康/天气）

**召回**（双层，`chat/memory.py`）：

1. **常驻注入**：每次对话把 (importance, created_at) 排序的前 5 条记忆以
   一行一条（含 entry_id，供 replaces 引用）注入 system prompt「近期记忆」
   段——近期事项确定性命中，不依赖模型自觉
2. **打分检索**：`recall(storage, keywords)` 纯函数打分——关键词重合(×3) +
   importance(×0.5) + 新近度(<7天 +2 / <30天 +1)，零重合不返回；关键词匹配
   含包含关系（「感冒」对「感冒药」）并延伸到标题/正文

跨话题关联的关键：FTS 字面检索无法把「出去玩」和「感冒」联系起来，本机制
靠**保存与检索两端都由 LLM 生成同一话题空间的场景关键词**来桥接语义鸿沟，
在 sqlite-vec（v0.2）落地前以零新依赖覆盖该场景。

### 7.2 向量混合检索（2026-09-01 增补，schema v5）

RAG 检索升级为**双通道混合**：FTS5（字面精确：代码/报错/API 名）+ 向量
（语义相似：同义改写）。「问『身份』但条目只有『学生』」这一 FTS 硬伤
（§13 风险触发器的真实案例）由向量通道原生解决。§7 的档案常驻注入与
§7.1 的关键词桥接均保留——前者保证画像类问题确定命中，后者可解释且是
常驻记忆注入的基础。

- **存储**：`entries_vec`（vec0，主键 entry_id + `float[1024]` cosine）。
  向量是**第三类索引**（与 FTS 同级）：md 仍是唯一事实来源，向量表随时
  可清空重建；sqlite-vec 扩展加载失败 → 整体降级纯 FTS（v4 行为），不阻塞启动
- **嵌入**：双 provider（OpenAI 兼容基类）——**GLM embedding-3**（复用 glm
  provider key、1024 维、批量 ≤64）或**硅基流动 BAAI/bge-m3**（免费档、原生
  1024 维与向量表匹配、批量 ≤32、独立 `embedding_api_key`）。settings
  `embedding_provider` 切换（`glm` 默认，key 为空回退 provider key）；key
  每次调用时从 settings 解析，后配免重启。出网内容 = 标题 + 正文前 1500 字
  → 所选服务商，与 LLM 对话同属本地直连。**两家向量空间不互通，切换
  provider 后必须重建索引**（设置页切换时有提示）
- **写入**：md/SQLite 事务提交**之后**补嵌；网络失败仅告警不阻断保存，
  缺口由 backfill（幂等可续跑）补齐。「重新索引」只清向量不重嵌——重嵌
  走设置页「重建索引」按钮，避免一键操作产生隐式 API 费用
- **融合**（`chat/rag.py`）：两通道各取 top 6，RRF 融合
  （score = Σ 1/(60+rank)，按 entry_id 去重）取 top 3——FTS rank 与
  cosine distance 量纲不可比，排名融合免归一化；向量通道当轮故障时
  退化为纯 FTS，不拖垮对话。citations / knowledge_refs 协议不变

**开关与交互**：settings `memory_enabled`（默认开）控制工具挂载与常驻注入；
自动保存推送 `memory_saved` SSE → 前端轻量记忆卡片（标题 + 关键词 chips +
撤销=软删条目）；recall 命中推送 `memory_refs` → 「想起」chips。

### 7.3 语义空间三维视图（2026-09-01 增补）

把 §7.2 的向量索引再派生一层**可视视图**：1024 维向量降维到 3D，Library
「立体」tab 展示可交互点云（旋转/缩放/悬停 tooltip/点击跳转条目），按合集
着色。**纯本地计算、零出网**——只读已存向量、不依赖 embedder（删了 key
图仍在）；md/向量表/业务表零改动。

- **降维管线**（`projection.py`，scikit-learn）：L2 归一化 → PCA 预降维到
  min(50, n-1) 维 → t-SNE 3D（cosine、pca init、`random_state=42`、自适应
  perplexity=min(30, (n-1)/3)）。PCA 预处理是关键：高维原始向量上直接
  t-SNE 优化不稳（实测小样本退化为球壳散点），预处理后同输入必同输出。
  条目 <3 不投影；3≤n<20 或 >5000 直接 PCA 兜底。坐标以质心为中心等比
  缩放进 [-1, 1] 立方体
- **缓存**：坐标不落库（派生视图的派生视图），进程内存缓存，签名 =
  (embedding provider, model, 向量数, 条目数, MAX(updated_at))——增删改
  条目或切换 embedding provider 后首次 GET 自动重算；另有 POST refresh
  强制重算。数百条规模全量重算 1~2s（实测 300 点 0.8s）
- **前端**：three.js + @react-three/fiber（v9，React 19 兼容）+ drei
  OrbitControls；Points + 径向渐变软粒子贴图 + AdditiveBlending 呈辉光感
  （无后处理）；合集→颜色为纯函数（全量合集名排序稳定取色，点色取首个
  合集）；图例点击隐藏/显示合集；WebGL 不可用 / 条目不足 / vec 扩展缺失
  → 对应空态降级
- **已知局限**：t-SNE 布局随库内容变化整体漂移（固定 seed 只保证同输入
  同输出，属算法固有属性）；极小样本 + 极少簇数下 3D t-SNE 有球壳退化
  倾向（真实库主题数远多于 2，实测 4 簇 48 点簇间/簇内距离比 ~1.6x）

---

## 8. 前端设计

### 8.1 页面与组件

```
frontend/src/
  pages/
    ChatPage.tsx          # 默认页：左会话列表 + 主对话区
    LibraryPage.tsx       # 知识库：列表/立体双 tab（立体 = 语义空间三维点云，§7.3）
    MemoriesPage.tsx      # 记忆管理（2026-09-06 增补）：「记忆」合集集中管理——
                          # 重要度排序 + 关键词搜索 + 展开编辑（标题/内容/关键词/
                          # 重要度，复用 PUT /entries）+ 删除；对标 ChatGPT Memory
    EntryDetailPage.tsx   # 详情 + 元数据 + 反向链接 + 来源徽标(source=chat 可跳回会话)
    EntryEditPage.tsx     # 表单 + CodeMirror
    SettingsPage.tsx      # Provider/key/模型/RAG 默认/vault 路径/连通测试
  components/
    chat/    SessionSidebar · MessageBubble(markdown+shiki 流式渲染) · ChatInput
             SavedCard · SuggestCard(确认/忽略) · CitationChips · RagToggle
    library/ VectorGraph(语义空间三维点云，§7.3) · pointColors(合集配色纯函数)
    editor/  FrontmatterForm · CodeMirrorEditor
    common/  MarkdownView · GlassPanel(毛玻璃容器) · GradientText
  stores/   chatStore · settingsStore · libraryStore   (zustand)
  api/      client.ts · sse.ts(fetch+ReadableStream 解析)
```

### 8.2 布局与视觉

- 左侧栏：导航（对话/知识库/记忆/设置）+ 会话列表/条目列表，`backdrop-blur` 毛玻璃
- 主区：对话气泡大圆角、渐变边框；AI 回答区 `react-markdown` + shiki 深色主题
- 动效（motion）：消息淡入上浮、流式光标、卡片悬浮位移
- 默认暗色玻璃拟态；`--kc-*` CSS variables + `html[data-theme="light"]` 支持明暗切换
  （设置页「外观」可选，localStorage `kc-theme` 持久化，详见 TECH_STACK.md §4）

---

## 9. 安全与隐私（2026-09-07 P0 加固后）

| 维度 | 策略 |
|---|---|
| 数据边界 | 知识 md + SQLite + 对话历史全本地；仅调 LLM API 出网 |
| 服务绑定 | `127.0.0.1` only |
| 本地鉴权 | 可选：环境变量 `KATE_API_TOKEN` 启用后所有 /api 请求须携带 `X-Kate-Token` 头 / `Authorization: Bearer` / `?api_token=`（`<img>` 场景），`/api/health` 豁免（sidecar 探测）；token 由 Electron sidecar 启动时生成注入，未设置则不启用（dev 手动起后端不变） |
| API key | settings 表中经 **Windows DPAPI 加密**（`dpapi:` 前缀密文，仅当前用户可解，security.py），写侧加密读侧解密对调用方透明；历史明文启动时自动迁移；不入 vault、不进 md、不打日志 |
| 出网内容 | 用户消息 + system prompt（含 RAG 检索片段）发给所选 provider——切换 provider 即切换数据去向 |
| 软删除 | `.trash/` 完整回收站（2026-09-07）：`GET /api/trash` 列表 + 恢复 + `DELETE /api/trash/:id` 彻底删除；保留 30 天，启动时自动清理超期文件 |
| 备份 | 用户自行 git 管理 vault |

---

## 10. 测试策略

| 层 | 内容 |
|---|---|
| 后端单测 | frontmatter / linking / storage / search（jieba 切词、中文查询）/ providers（mock，含流式 tool_calls 拼接归一化） |
| 后端集成 | entries CRUD API；chat SSE 全链路（fake provider 按脚本吐 delta + tool_call）；save_knowledge 入库产物校验 |
| 前端 | Vitest 组件测试（保存卡片、建议卡片确认流、流式渲染）；E2E 可选 Playwright |
| 手动验证 | Electron sidecar 起停、真实 provider 对话 |

---

## 11. 项目结构

```
Kate-Cortex/
├── docs/                       # REQUIREMENTS / DESIGN / TECH_STACK
├── backend/
│   ├── pyproject.toml          # uv 管理
│   ├── src/kate_cortex/
│   │   ├── main.py             # FastAPI app
│   │   ├── config.py
│   │   ├── db.py               # SQLite 连接 + schema + migration
│   │   ├── models.py           # Pydantic
│   │   ├── storage.py          # md ↔ SQLite 双写
│   │   ├── frontmatter.py
│   │   ├── linking.py
│   │   ├── search.py           # FTS5 + jieba
│   │   ├── chat/
│   │   │   ├── service.py      # agent loop + 会话管理
│   │   │   ├── prompts.py
│   │   │   └── rag.py
│   │   ├── skills/
│   │   │   └── knowledge.py    # save_knowledge / suggest_save
│   │   ├── routes/
│   │   │   ├── entries.py · collections.py · chat.py · settings.py · sync.py
│   │   └── providers/
│   │       ├── base.py · deepseek.py · glm.py
│   └── tests/
├── frontend/                   # electron-vite
│   ├── electron/
│   │   ├── main.ts             # 窗口 + 系统集成
│   │   ├── sidecar.ts          # Python 进程管理
│   │   └── preload.ts
│   ├── src/                    # React（见 §8.1）
│   ├── electron.vite.config.ts
│   └── package.json
└── vault/                      # 用户数据（git ignore 实际内容）
```

---

## 12. 实施路线图

| 阶段 | 内容 | 预估 |
|---|---|---|
| 1 | 后端知识库骨架：db / frontmatter / storage / search(FTS5+jieba) / entries CRUD + 测试 | 1 天 |
| 2 | Provider 层 + 对话模块：conversations/messages、SSE 流式、会话 API + 测试 | 1.5 天 |
| 3 | 收集 skill：save_knowledge / suggest_save、agent loop、RAG 注入 + 测试 | 1 天 |
| 4 | 前端：electron-vite 脚手架、暗色玻璃拟态主题、对话页、知识库页、设置页 | 2 天 |
| 5 | Electron sidecar 桥接、RAG 引用展示打磨、PyInstaller + electron-builder 打包 | 1 天 |

MVP 合计 6~7 人天。

---

## 13. 风险与对策

| 风险 | 对策 |
|---|---|
| DeepSeek/GLM 流式 tool_calls 增量格式差异 | Provider 层归一化为 StreamEvent，mock 集成测试覆盖两家 |
| jieba 分词质量影响搜索/RAG 召回 | MVP 够用；v0.2 向量检索补位 |
| PyInstaller 体积大 / 杀软误报 | 打包延后到阶段 5；个人自用可接受 |
| SSE 中断 / 用户停止生成 | AbortController + 后端 task 取消；以 `done` 事件为落库边界 |
| 长对话上下文超限 | MVP 截断最近 20 轮；v0.2 做摘要压缩 |
| md/SQLite 双写不一致 | 沿用：启动 sync 校验 + 手动重新索引 |
| 中文 slug | 拼音转换，冲突/失败时时间戳兜底 |

---

## 14. 未决问题

- [x] vault 默认路径（2026-08-17 拍板）：开发期 `<repo>/vault/`；打包版
  `%USERPROFILE%\Kate-Cortex\vault`；config + settings 可覆盖
- [ ] 对话历史导出 markdown 的格式（v0.2）
- [ ] RAG 注入条数 / token 预算实测调参（当前 3 条 / 2000 tokens 为拍板值）
- [x] API key 明文问题（2026-09-07 解决）：settings 表凭据经 Windows DPAPI
  加密存储（security.py），历史明文启动时自动迁移；OS keyring 不再需要
- [x] embedding provider 选型（2026-09-01 拍板）：GLM embedding-3——OpenAI 兼容、
  复用现有 glm key 用户零新配置、支持 1024 维（见 §7.2）；硅基流动/本地模型留扩展位
- [x] 项目名：维持 Kate-Cortex（2026-08-17 拍板）

---

## 15. MCP 服务端（2026-09-07 增补）

「桌面端 + MCP 双形态」的服务端侧：外部编码 agent（Claude Code / Cursor）经
stdio 调用 Kate-Cortex 的知识库与记忆能力。与 MCP 客户端（`mcp_client.py`，
Kate 在对话里调高德等外部工具）方向相反——客户端是"你用别人的工具"，
服务端是"别人用你的数据"。

- **进程形态**：`uv run kate-cortex-mcp`（`mcp_server.py`，mcp SDK 2.x
  MCPServer + stdio），与 1738 HTTP 服务并存，SQLite WAL 支持多进程同库读写；
  不占端口、不出网
- **工具**（6 个，全部复用现有层）：`search_knowledge`（rag.retrieve 混合检索）·
  `get_entry`（全文+反向链接）· `save_knowledge`（source=import）·
  `list_collections` · `recall_memory`（chat.memory.recall）·
  `save_memory`（keywords/importance，replaces 覆盖更新）
- **约束**：只增不改（无 update/delete 工具，append-only 与记忆机制同原则）；
  外部写入一律 `source=import` 打标，与 manual/chat 区分可追溯
- **接入**：`claude mcp add kate-cortex -s user -- uv run --project
  <backend 目录> python -m kate_cortex.mcp_server`

---

## 16. 云端多用户形态（2026-09-11 增补）

与「本地优先」互补的第二形态：一台常驻服务器跑 Docker，浏览器/微信直接用，
数据按账号隔离持久存储。**双模式由 `KATE_DATA_DIR` 是否设置决定**，单用户形态
（桌面 sidecar / dev / Vercel 试用）零改动：

- **运行模式**：未设 `KATE_DATA_DIR` → 单用户（启动装配一套全局服务到 app.state，
  可选 KATE_API_TOKEN）；设置后 → 多用户（不打开任何单用户库，会话中间件按
  cookie 鉴权，每请求注入该用户服务集）
- **数据布局**：`<KATE_DATA_DIR>/users.sqlite`（账号 + 会话表，全局一个）+
  `<KATE_DATA_DIR>/users/<user_id>/vault/`（每用户独立 vault，index.sqlite 在内，
  沿用现有约定——FTS5/jieba/sqlite-vec 全部按连接工作，检索层零重写）
- **认证**（`auth.py` + `routes/auth.py`）：用户名 + 口令（scrypt，stdlib）；
  注册校验邀请码（env `KATE_INVITE_CODE`，设了才启用）；会话 token 随机 32B
  走 HttpOnly cookie（`kate_session`，SameSite=Lax，`KATE_COOKIE_SECURE=1` 加
  Secure），库存 SHA256，30 天滑动过期；`/api/health`、`/api/auth/*` 豁免
- **每用户服务**（`multiuser.py`）：`UserServices` 八件套（config/db/storage/
  chat_service/settings_service/provider_factory/vector_index/projection）与单用户
  create_app 装配同构，抽出的 `initialize_storage`（启动迁移）每用户首次构建时
  执行；`UserRegistry` 进程内 LRU（上限 64，锁保护，逐出即关连接）。路由统一经
  `get_services(request)` 取服务：多用户从 `request.state.svc`，单用户回落
  `app.state`——路由代码不感知模式
- **密钥加密**：`security.py` 双通道——Windows DPAPI（桌面）；Linux 服务器
  `KATE_SECRET_KEY`（任意随机串 sha256 → Fernet key，`fernet:` 前缀），未配置
  明文 + 启动告警；解密兼容 dpapi:/fernet:/明文，`encrypt_existing_secrets`
  迁移自动重写为当前平台形态
- **SSRF 防护**（`mcp_registry.assert_public_endpoint`）：多用户模式下 MCP 接入
  与调用前解析域名，内网/环回/链路本地地址一律拒绝（模型可能被网页内容诱导
  让服务器访问内网）；单用户默认不启用（本机接 localhost MCP 合法），
  `KATE_MCP_ALLOW_PRIVATE=1` 强制关闭
- **前端**：`AuthGate` 分流——Electron（preload 注入 kateRuntime）直通应用壳；
  Web 形态启动查 `/api/auth/me`，未登录只见登录页。401 全局拦截：client.ts
  `request()` 单点回调（`setUnauthorizedHandler`）+ sse.ts / testProvider 裸
  fetch 补齐 → 清空登录态切登录页。Web 构建同源 `/api`，cookie 自动携带零改动
- **静态托管**：多用户模式下 `KATE_FRONTEND_DIR` 存在即 mount StaticFiles
  （hash 路由无需 SPA rewrite），单进程同时服务前端与 /api，免 CORS
- **部署**：多阶段 Dockerfile（node build:web → python slim + pip install backend，
  `PIP_INDEX_URL` 可换国内源）+ docker-compose（卷 `./.data:/data`，env 邀请码/
  主密钥/Secure cookie）；备份 = 备份数据目录
- **v1 边界**：无邮箱验证/找回密码、无每用户配额、无管理后台；jieba 词典为
  进程级共享（只读，天然多用户安全），用户逐出仅在 LRU 溢出时发生

---

## 附录 A：参考项目

| 项目 | 借鉴点 |
|---|---|
| [Cherry Studio](https://github.com/cherryhq/cherry-studio) | Electron + React 的 AI 桌面客户端形态、多 provider 管理、知识库功能 |
| [LobeChat](https://github.com/lobehub/lobe-chat) | 对话 UI/UX、主题系统 |
| [mem0](https://github.com/mem0ai/mem0) | 对话→知识的抽取/总结 prompt 设计 |
| [Obsidian](https://obsidian.md/) | 双向链接、frontmatter 范式 |
