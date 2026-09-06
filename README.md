# Kate-Cortex

> 个人编程知识库 agent · 本地优先 · 桌面端 + MCP 双形态

把日常工作里散落的代码片段、踩坑记录、架构决策、学习笔记、随手粘贴的内容，
沉淀成**人类可读、可检索、可被 agent 调用**的结构化资产。

## 状态

`v0.1 设计中` — 见 [docs/DESIGN.md](./docs/DESIGN.md)

## 核心特性（MVP 目标）

- **四种知识类型**：`snippet` / `decision` / `note` / `clip`
- **Markdown 优先**：每条知识就是一个 .md 文件，可手动编辑、可 git
- **桌面端**：Tauri + React，本地运行
- **结构化检索**：标签、项目、类型过滤 + 全文搜索
- **双向链接**：`[[slug]]` 自动关联

## 后续路线

- v0.2：GLM/DeepSeek 对话；向量语义检索已实现（2026-09-01，FTS5 + sqlite-vec
  混合检索，GLM embedding-3，见 [DESIGN.md §7.2](./docs/DESIGN.md)）；语义空间
  三维视图已实现（2026-09-01，知识库「立体」tab，t-SNE 降维点云，见
  [DESIGN.md §7.3](./docs/DESIGN.md)）；MCP client 已实现（2026-09-02，Streamable
  HTTP 接入外部工具服务，如高德地图 MCP——POI / 路线 / 天气实时查询，可在对话里
  做旅游行程规划并输出 Markdown，见 [DESIGN.md §6.3](./docs/DESIGN.md)）
- v0.3：MCP server 已实现（2026-09-07，stdio 暴露 6 个工具——知识检索/读取/沉淀、
  合集列表、记忆召回/保存，外部 agent 写入打 source=import 标，见
  [DESIGN.md §15](./docs/DESIGN.md)）。Claude Code 接入：
  `claude mcp add kate-cortex -s user -- uv run --project <backend目录> python -m kate_cortex.mcp_server`

## 技术栈

| 层 | 技术 |
|---|---|
| 桌面壳 | Tauri 2.0 |
| 前端 | React + TypeScript + Tailwind + CodeMirror；三维视图 three.js + react-three-fiber |
| 后端 | Python 3.12 + FastAPI；三维投影 scikit-learn（t-SNE/PCA） |
| 存储 | SQLite + sqlite-vec |
| LLM | GLM / DeepSeek / 硅基流动 / 魔搭（OpenAI 兼容）；免费组合：glm-4.7-flash（智谱免费）· Qwen3-8B（硅基流动免费档）· 魔搭每日 2000 次；向量检索：GLM embedding-3 或硅基流动 bge-m3（免费） |

详见 [设计文档](./docs/DESIGN.md)。

## 开发（待实现）

```bash
# 后端
cd backend && uv sync && uv run uvicorn kate_cortex.main:app --reload

# 前端
cd frontend && pnpm install && pnpm tauri dev
```

## License

MIT
