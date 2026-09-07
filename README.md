# Kate-Cortex

> 个人编程知识库 agent · 本地优先 · 桌面端 + MCP 双形态

把日常工作里散落的代码片段、踩坑记录、架构决策、学习笔记、随手粘贴的内容，
沉淀成**人类可读、可检索、可被 agent 调用**的结构化资产。

## 状态

`v0.1 可用` — 对话即沉淀的完整闭环 + Windows 安装包。详见 [docs/DESIGN.md](./docs/DESIGN.md)

## 核心特性

- **对话即沉淀**：与 Kate（AI）对话，说「记一下」即入库；AI 也会主动建议保存；
  自动记忆跨话题召回（健康/计划/偏好），记忆管理页集中管理
- **Markdown 优先**：每条知识就是一个 .md 文件，frontmatter 元数据 + 合集组织 +
  `[[slug]]` 双向链接，可手动编辑、可 git、回收站 30 天可恢复
- **混合检索**：FTS5（jieba 中文分词）+ sqlite-vec 向量语义检索（GLM embedding-3
  或硅基流动 bge-m3 免费档），换个说法也能搜到；语义空间三维视图
- **多模态**：对话可粘贴/拖入图片提问（glm-5.3 等视觉模型）
- **MCP 双形态**：客户端接入高德等外部工具；服务端（stdio）向 Claude Code /
  Cursor 暴露知识检索、沉淀与记忆工具
- **多模型**：DeepSeek / GLM / GLM 编程套餐 / 硅基流动 / 魔搭，全部本地 key 直连
- **安全**：API key DPAPI 加密落盘，本地 API token 鉴权，数据全本地

## 桌面端（Electron + Python sidecar）

日常开发模式（自动拉起后端 sidecar + token 鉴权）：

```bash
cd frontend && pnpm dev          # Electron 主进程 spawn 后端并等待就绪
```

也可手动起后端（调试用）：`cd backend && uv run uvicorn kate_cortex.main:app --port 1738`

## 打包分发（Windows）

```bash
# 1. 后端 → onefile exe（jieba 词典 / sqlite-vec / sklearn 已收集）
cd backend && uv run pyinstaller kate_cortex.spec --noconfirm

# 2. 前端 + NSIS 安装包（国内网络需镜像环境变量，见 docs/IMPLEMENTATION_PLAN 阶段 5）
cd frontend && pnpm build && pnpm exec electron-builder --win
```

产物：`frontend/release/Kate-Cortex-Setup-<version>.exe`（另有 `win-unpacked/` 免安装直跑）。
打包版数据目录：`%USERPROFILE%\Kate-Cortex\vault`。

## Claude Code 接入（MCP 服务端）

```
claude mcp add kate-cortex -s user -- uv run --project <backend目录> python -m kate_cortex.mcp_server
```

暴露 6 个工具：search_knowledge / get_entry / save_knowledge / list_collections /
recall_memory / save_memory（详见 [DESIGN.md §15](./docs/DESIGN.md)）。

## 技术栈

| 层 | 技术 |
|---|---|
| 桌面壳 | Electron 39（electron-vite）+ Python sidecar（PyInstaller onefile） |
| 前端 | React + TypeScript + Tailwind + CodeMirror；三维视图 three.js + react-three-fiber |
| 后端 | Python 3.12 + FastAPI；三维投影 scikit-learn（t-SNE/PCA） |
| 存储 | SQLite + sqlite-vec（FTS5 + 向量混合检索） |
| LLM | GLM / DeepSeek / 硅基流动 / 魔搭（OpenAI 兼容）；GLM 编程套餐（Anthropic 协议）；向量：GLM embedding-3 或硅基流动 bge-m3（免费） |
| 协议 | MCP 客户端（Streamable HTTP）+ MCP 服务端（stdio） |

详见 [设计文档](./docs/DESIGN.md)。

## License

MIT
