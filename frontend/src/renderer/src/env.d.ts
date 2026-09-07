/// <reference types="vite/client" />

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
