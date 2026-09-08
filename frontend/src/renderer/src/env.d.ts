/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Web 构建（Vercel）的后端地址，如 /api（同源）或 https://xxx/api；Electron 内不设置 */
  readonly VITE_API_BASE?: string
  /** 远程部署的后端访问令牌（与 KATE_API_TOKEN 配对）；Electron 内用 preload 注入的 token */
  readonly VITE_API_TOKEN?: string
}

export {}

declare global {
  interface KateRuntime {
    apiPort: number
    apiToken?: string
  }
  interface Window {
    /** preload 暴露（Electron 内）；纯 vite/测试环境下不存在，走默认值 */
    api?: { kateRuntime: KateRuntime }
  }
}
