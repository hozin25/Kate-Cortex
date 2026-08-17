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

- v0.2：向量语义检索 + GLM/DeepSeek 对话
- v0.3：MCP server，被 Claude Code 调用，自动沉淀任务总结

## 技术栈

| 层 | 技术 |
|---|---|
| 桌面壳 | Tauri 2.0 |
| 前端 | React + TypeScript + Tailwind + CodeMirror |
| 后端 | Python 3.12 + FastAPI |
| 存储 | SQLite + sqlite-vec |
| LLM | GLM / DeepSeek（OpenAI 兼容） |

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
