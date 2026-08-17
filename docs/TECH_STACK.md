# Kate-Cortex 技术栈选型

> 选型结论记录 · 确定于 2026-08-17 · 配套 [REQUIREMENTS.md](./REQUIREMENTS.md)
>
> 注：桌面壳由原设计的 Tauri 改为 Electron（2026-08-17 决策），
> DESIGN.md 中与 Tauri 相关的章节待重写。

---

## 1. 选型总表

| 层 | 选择 | 版本基线 | 为什么是它 | 为什么不是另一个 |
|---|---|---|---|---|
| 桌面壳 | **Electron** | latest | 生态最成熟（Cherry Studio 同款路线）；Node 主进程管理 Python sidecar 简单；自带 Chromium 渲染一致；自动更新/tray/通知开箱即用 | Tauri 更轻（体积小 20-50x、内存省 5x），但需要 Rust 工具链、WebView2 兼容性需自己兜底；个人项目优先开发效率 |
| 前端框架 | **React + TypeScript + Vite** | React 19 | AI 聊天类应用事实标准（Cherry Studio / LobeChat / NextChat 全是 React），现成设计与组件可参考最多 | Vue 3 国内主流，但 AI 聊天生态几乎全在 React 侧 |
| UI 体系 | **Tailwind CSS + shadcn/ui** | Tailwind 4 | shadcn 是 AI 界面组件生态的底座（AI Elements 等均基于它）；代码进仓库可深度定制炫酷样式 | Ant Design / Naive UI 风格固定，难做玻璃拟态定制 |
| 动效 | **motion**（原 framer-motion） | latest | 流式输出、卡片过渡、侧栏动画；React 生态动效标准 | GSAP 偏重，交互 UI 用不上其全部能力 |
| 视觉风格 | **暗色玻璃拟态** | — | 深色底 + backdrop-blur 毛玻璃 + 渐变光晕 + 大圆角，Raycast/Arc 方向；支持明暗切换，默认暗色 | 明亮简洁风耐看但不炫；终端风程序员辨识度高但阅读疲劳 |
| 代码高亮 | **shiki** | latest | VSCode 同款引擎，主题质感最好，聊天代码块的炫酷担当 | highlight.js 主题质量差一档 |
| Markdown | **react-markdown + remark-gfm + KaTeX** | latest | 流式安全渲染（不注入 HTML）、GFM 表格、数学公式 | |
| 编辑器 | **CodeMirror 6** | 6.x | markdown 模式 + 代码块高亮，知识库编辑用 | Milkdown/TipTap 更炫但重、行为不可控 |
| 图标 | **lucide-react** | latest | shadcn 标配 | |
| 后端 | **Python + FastAPI** | 3.12+ / 0.115+ | AI 生态无可替代：openai SDK、embedding、RAG pipeline；异步 + SSE 原生支持；自带 OpenAPI 文档 | 全 Rust 无 sidecar 最干净但开发慢、LLM 生态弱；Node 在 RAG 侧无优势 |
| 包管理 | **uv** | latest | Python 侧依赖与虚拟环境管理，极快 | |
| LLM 接入 | **openai SDK + base_url 切换** | latest | DeepSeek / GLM 均兼容 OpenAI 协议，一个 SDK 通过不同 base_url + api_key 切换，无需 litellm 这类重依赖 | litellm 支持 100+ provider，但我们只需要 2 家，白付复杂度 |
| 数据库 | **SQLite** | 3.45+ | 本地单文件；FTS5 全文 + sqlite-vec 向量（v0.2） | |
| 中文检索 | **FTS5 + jieba 预分词** | — | FTS5 默认分词器不支持中文，入库时用 jieba 分词后写入索引列 | **已知风险**：分词质量决定搜索体验，jieba 是主流稳妥解 |
| 打包 | **electron-builder + PyInstaller** | latest | electron-builder 出 Windows nsis 安装包；PyInstaller 把 Python 服务打成单文件 exe 作为 sidecar | |

## 2. 架构与进程模型

```
Electron 主进程 (Node.js, TypeScript)
  │
  ├─ app 启动 → spawn Python sidecar
  │     开发: uv run uvicorn kate_cortex.main:app --port 1738
  │     生产: resources/kate-cortex-server.exe   (PyInstaller onefile)
  │     轮询 /api/health 就绪后才创建窗口
  │     app 退出 → kill sidecar
  │
  └─ BrowserWindow (React)
        dev:  loadUrl(http://localhost:5173)   ← Vite dev server
        prod: loadFile(打包产物)
        所有业务请求 → http://127.0.0.1:1738
```

- 脚手架用 **electron-vite**（整合 Vite + Electron + TS 的主流方案）
- API 只绑 `127.0.0.1`，不对外网暴露
- 对话流式输出走 **SSE**（`StreamingResponse`），前端 `fetch` + `ReadableStream` 解析

## 3. LLM Provider 接入

```
providers/
  base.py      # Provider 抽象 + 配置结构
  deepseek.py  # base_url = https://api.deepseek.com/v1
  glm.py       # base_url = https://open.bigmodel.cn/api/paas/v4
```

- 统一走 openai SDK：`OpenAI(base_url=..., api_key=...)`
- 两者均支持 OpenAI tools 协议 → `save_knowledge` / `suggest_save` 工具用 function calling 实现
- API key 存本地配置文件（MVP），不上传、不入 markdown

## 4. 暗色玻璃拟态·设计基调

| 要素 | 做法 |
|---|---|
| 底色 | 深色（zinc-950 级），多层表面用半透明叠加 |
| 毛玻璃 | `backdrop-blur` + 半透明边框（white/10） |
| 渐变光晕 | 主色渐变（indigo→cyan 之类）用于光晕、边框流光、logo |
| 圆角 | 大圆角（rounded-xl 起），气泡 rounded-2xl |
| 动效 | motion：消息淡入上浮、流式光标闪烁、侧栏 item 悬浮位移 |
| 代码块 | shiki 深色主题（如 tokyo-night / velleda 之类自选） |
| 明暗 | CSS variables + `.dark` 类切换，默认暗色 |

## 5. 打包策略（重要：延后处理）

- **开发期完全不打包**：Electron dev 模式直接 `uv run` 拉 Python 服务，免 PyInstaller 调试地狱
- 最后阶段才做：PyInstaller `--onefile` 打 server → electron-builder `extraResources` 塞进安装包
- 已知风险：PyInstaller 产物 100MB+ 级、个别杀软误报（个人自用可接受）

## 6. 前端关键库清单

| 用途 | 库 |
|---|---|
| 路由 | react-router |
| 状态 | zustand（会话列表、设置、UI 状态） |
| 服务端数据 | 自己封 fetch client（规模小，不上 react-query） |
| 表单 | react-hook-form + zod（设置页、条目表单） |
| 聊天流式 | 自封 useChatStream（SSE 解析 + 中断控制） |
