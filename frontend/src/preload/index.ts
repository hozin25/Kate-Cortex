import { contextBridge } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

// 主进程经 additionalArguments 传入后端端口与鉴权 token（sidecar 启动时生成）
function readFlag(name: string): string | undefined {
  const prefix = `--${name}=`
  const hit = process.argv.find((arg) => arg.startsWith(prefix))
  return hit ? hit.slice(prefix.length) : undefined
}

const kateRuntime = {
  apiPort: Number(readFlag('kate-port')) || 1738,
  apiToken: readFlag('kate-token') || undefined
}

const api = { kateRuntime }

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('api', api)
  } catch (error) {
    console.error(error)
  }
} else {
  // @ts-ignore (define in dts)
  window.electron = electronAPI
  // @ts-ignore (define in dts)
  window.api = api
}
