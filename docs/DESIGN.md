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
│   ├─ /api/tags      标签                                       │
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
│   ├─ index.sqlite   条目/标签/链接/FTS 索引 + 对话历史         │
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
type: howto
title: Redis pipeline 在事务模式下不返回结果
tags: [redis, bug]
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
| `type` | **改为** `note` / `clip` / `decision` / `howto`（snippet 泛化为 howto） |
| `language` | 降为可选元数据（不再绑定独立类型） |
| `source` | **改为** `manual` / `chat` / `import` |
| `conversation` | **新增**，可选。对话沉淀时记录来源会话，详情页可跳回 |

### 3.3 SQLite Schema

```sql
-- ── 知识库（沿用 v0.1，type/source 枚举更新，新增 conversation_id）──
CREATE TABLE entries (
  id              TEXT PRIMARY KEY,     -- kc_YYYYMMDD_NNN
  slug            TEXT UNIQUE NOT NULL,
  title           TEXT NOT NULL,
  type            TEXT NOT NULL CHECK (type IN ('note','clip','decision','howto')),
  project         TEXT,
  language        TEXT,
  source          TEXT NOT NULL CHECK (source IN ('manual','chat','import')),
  conversation_id TEXT,                 -- 对话沉淀时记录
  file_path       TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE INDEX idx_entries_type    ON entries(type);
CREATE INDEX idx_entries_created ON entries(created_at DESC);
CREATE INDEX idx_entries_conv    ON entries(conversation_id);

CREATE TABLE tags (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL
);

CREATE TABLE entry_tags (
  entry_id TEXT NOT NULL,
  tag_id   INTEGER NOT NULL,
  PRIMARY KEY (entry_id, tag_id),
  FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id)   REFERENCES tags(id)    ON DELETE CASCADE
);

CREATE TABLE links (
  from_id TEXT NOT NULL,
  to_id   TEXT NOT NULL,
  relation TEXT,
  PRIMARY KEY (from_id, to_id),
  FOREIGN KEY (from_id) REFERENCES entries(id) ON DELETE CASCADE,
  FOREIGN KEY (to_id)   REFERENCES entries(id) ON DELETE CASCADE
);

-- ── 中文全文检索：FTS5 + jieba 预分词 ──
-- 写入时 title/content/tags 经 jieba 切词、空格连接后存入 *_tokens 列；
-- 查询时对关键词同样切词后 MATCH
CREATE VIRTUAL TABLE entries_fts USING fts5(
  title_tokens,
  content_tokens,
  tag_tokens,
  entry_id UNINDEXED
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

---

## 4. API 设计

### 4.1 端点总览

```
# 知识库
POST   /api/entries                     创建
GET    /api/entries                     ?type=&tag=&q=&limit=&offset=
GET    /api/entries/:id
PUT    /api/entries/:id
DELETE /api/entries/:id                 软删除
POST   /api/entries/:id/restore         从 .trash 恢复
GET    /api/entries/:id/links           反向链接

# 标签
GET    /api/tags
DELETE /api/tags/:name

# 对话
POST   /api/chat/sessions               {provider, model, title?}
GET    /api/chat/sessions               列表（含最近消息预览）
PATCH  /api/chat/sessions/:id           重命名
DELETE /api/chat/sessions/:id
GET    /api/chat/sessions/:id/messages  历史
POST   /api/chat/sessions/:id/chat      发消息 → SSE 流式响应

# 设置
GET    /api/settings
PUT    /api/settings                    provider keys / 默认模型 / RAG 默认 / vault 路径
POST   /api/providers/test              {provider} 连通性测试

# 系统
POST   /api/sync                        重新索引
GET    /api/health                      {app: "kate-cortex", version}
```

### 4.2 SSE 事件协议（`POST /api/chat/sessions/:id/chat`）

请求：`{"content": "用户消息", "rag_enabled": true}`，响应 `text/event-stream`：

| event | data | 说明 |
|---|---|---|
| `citations` | `{entries: [{id, title, slug}]}` | 消息开始，RAG 命中的条目 |
| `delta` | `{text}` | 流式文本片段 |
| `tool_result` | `{entry_id, title, type, tags}` | save_knowledge 已入库 → 前端渲染保存卡片 |
| `suggest` | `{title, type, tags, preview}` | AI 建议卡片（**未入库**，等用户确认） |
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
  base.py      # Provider 抽象：chat_stream(messages, tools) -> AsyncIterator[StreamEvent]
  deepseek.py  # base_url = https://api.deepseek.com/v1
  glm.py       # base_url = https://open.bigmodel.cn/api/paas/v4
```

- 统一用 **openai SDK**，`OpenAI(base_url=..., api_key=...)` 切换两家
- `StreamEvent` 归一化两类事件：`TextDelta` / `ToolCallDelta`——**屏蔽两家在流式
  tool_calls 增量拼接上的格式差异**（这是已知的实现坑，Provider 层集中处理并配集成测试）
- API key 从 settings 读取；缺 key 时创建会话即报错（fail fast）
- embedding（v0.2）：GLM embedding-3 或硅基流动，接口在 base.py 预留

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
    "type": "note | clip | decision | howto",
    "tags": ["标签，3~5 个，小写"],
    "content_markdown": "总结后的正文。聚焦当前讨论主题，保留结论/方法/代码，剔除寒暄与过程。"
  }
}
```

**suggest_save**（AI 主动触发，仅生成建议）：

参数同上。description：*"当对话中出现值得长期保留的结论、方法或决策（即使用户没要求），
调用此工具生成保存建议，交由用户确认。不要在用户没确认前真正保存。"*

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
[RAG 知识（可选注入）：以下来自用户知识库，回答可参考并注明来源条目标题]
```

---

## 7. RAG 检索

- 触发：`rag_enabled=true`（全局默认开，会话内可切）时，每条用户消息发送前检索
- 检索：消息 jieba 分词 → `entries_fts` MATCH → top 3，每条截取前 ~500 字，
  总预算 ≤ 2000 tokens
- 注入：作为 system prompt 尾部知识段；`messages.knowledge_refs` 记录命中 id，
  前端渲染引用 chips（点击跳条目详情）
- v0.2：sqlite-vec 向量召回 + 关键词混合

---

## 8. 前端设计

### 8.1 页面与组件

```
frontend/src/
  pages/
    ChatPage.tsx          # 默认页：左会话列表 + 主对话区
    LibraryPage.tsx       # 知识库：过滤条 + 卡片列表
    EntryDetailPage.tsx   # 详情 + 元数据 + 反向链接 + 来源徽标(source=chat 可跳回会话)
    EntryEditPage.tsx     # 表单 + CodeMirror
    SettingsPage.tsx      # Provider/key/模型/RAG 默认/vault 路径/连通测试
  components/
    chat/    SessionSidebar · MessageBubble(markdown+shiki 流式渲染) · ChatInput
             SavedCard · SuggestCard(确认/忽略) · CitationChips · RagToggle
    library/ EntryList · FilterBar · SearchBox · EntryCard
    editor/  FrontmatterForm · CodeMirrorEditor
    common/  MarkdownView · GlassPanel(毛玻璃容器) · GradientText
  stores/   chatStore · settingsStore · libraryStore   (zustand)
  api/      client.ts · sse.ts(fetch+ReadableStream 解析)
```

### 8.2 布局与视觉

- 左侧栏：导航（对话/知识库/设置）+ 会话列表/条目列表，`backdrop-blur` 毛玻璃
- 主区：对话气泡大圆角、渐变边框；AI 回答区 `react-markdown` + shiki 深色主题
- 动效（motion）：消息淡入上浮、流式光标、卡片悬浮位移
- 默认暗色玻璃拟态，CSS variables + `.dark` 切换支持明暗，详见 TECH_STACK.md §4

---

## 9. 安全与隐私

| 维度 | 策略 |
|---|---|
| 数据边界 | 知识 md + SQLite + 对话历史全本地；仅调 LLM API 出网 |
| 服务绑定 | `127.0.0.1` only |
| API key | settings 表 + 本地配置文件，不入 vault、不进 md、不打日志 |
| 出网内容 | 用户消息 + system prompt（含 RAG 检索片段）发给所选 provider——切换 provider 即切换数据去向 |
| 软删除 | `.trash/` 保留 30 天（可配置）后清理 |
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
│   │   │   ├── entries.py · tags.py · chat.py · settings.py · sync.py
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
- [ ] API key：MVP 明文 settings 表，何时升级 OS keyring
- [ ] embedding provider 选型（v0.2 前定）
- [x] 项目名：维持 Kate-Cortex（2026-08-17 拍板）

---

## 附录 A：参考项目

| 项目 | 借鉴点 |
|---|---|
| [Cherry Studio](https://github.com/cherryhq/cherry-studio) | Electron + React 的 AI 桌面客户端形态、多 provider 管理、知识库功能 |
| [LobeChat](https://github.com/lobehub/lobe-chat) | 对话 UI/UX、主题系统 |
| [mem0](https://github.com/mem0ai/mem0) | 对话→知识的抽取/总结 prompt 设计 |
| [Obsidian](https://obsidian.md/) | 双向链接、frontmatter 范式 |
