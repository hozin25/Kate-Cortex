/** 运行环境检测：Electron 渲染进程由 preload 注入 kateRuntime（--kate-port/--kate-token），
 *  纯 Web 构建（多用户版/本地 vite）没有。preload 先于渲染脚本执行，模块加载期取值安全 */
export interface KateRuntimeInfo {
  apiPort: number
  apiToken?: string
}

export function kateRuntime(): KateRuntimeInfo | undefined {
  return typeof window !== 'undefined' ? window.api?.kateRuntime : undefined
}

export const isElectron = Boolean(kateRuntime())
