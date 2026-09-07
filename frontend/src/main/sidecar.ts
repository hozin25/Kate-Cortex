import { spawn, type ChildProcess } from 'child_process'
import { randomBytes } from 'crypto'
import http from 'http'
import { app } from 'electron'
import { join } from 'path'

/** Python 后端 sidecar 生命周期管理（DESIGN §2.2 / IMPLEMENTATION_PLAN 5.1） */

const APP_ID = 'kate-cortex'
const BASE_PORT = 1738
const MAX_PORT_ATTEMPTS = 10
const STARTUP_TIMEOUT_MS = 60_000
const POLL_INTERVAL_MS = 400

export interface SidecarHandle {
  port: number
  token: string
  /** null = 复用了已在运行的本应用后端（上次未退干净） */
  child: ChildProcess | null
  stop: () => Promise<void>
}

function probeHealth(port: number, timeoutMs = 1500): Promise<{ ours: boolean } | null> {
  return new Promise((resolve) => {
    const req = http.get(
      { host: '127.0.0.1', port, path: '/api/health', timeout: timeoutMs },
      (res) => {
        let body = ''
        res.on('data', (chunk) => (body += chunk))
        res.on('end', () => {
          try {
            resolve({ ours: JSON.parse(body).app === APP_ID })
          } catch {
            resolve(null)
          }
        })
      }
    )
    req.on('error', () => resolve(null))
    req.on('timeout', () => {
      req.destroy()
      resolve(null)
    })
  })
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

function backendCommand(port: number): { command: string; args: string[]; cwd?: string } {
  if (app.isPackaged) {
    return {
      command: join(process.resourcesPath, 'sidecar', 'kate-cortex-server.exe'),
      args: ['--port', String(port)]
    }
  }
  return {
    command: 'uv',
    args: ['run', 'uvicorn', 'kate_cortex.main:app', '--port', String(port)],
    // dev：frontend 由 electron-vite 运行，backend 在仓库同级目录
    cwd: join(app.getAppPath(), '..', 'backend')
  }
}

/** 退出时树杀（uv run / PyInstaller onefile 都有子进程，单杀 pid 杀不干净） */
function killTree(pid: number): Promise<void> {
  return new Promise((resolve) => {
    if (process.platform === 'win32') {
      const killer = spawn('taskkill', ['/PID', String(pid), '/T', '/F'], {
        windowsHide: true
      })
      killer.on('close', () => resolve())
      killer.on('error', () => resolve())
    } else {
      try {
        process.kill(-pid, 'SIGTERM')
      } catch {
        /* 进程已退出 */
      }
      resolve()
    }
  })
}

export async function startSidecar(): Promise<SidecarHandle> {
  // 1) 端口探测：1738 起逐个尝试；健康响应是本应用 → 复用（幂等），否则避让
  let port = BASE_PORT
  let reuse = false
  for (let i = 0; i < MAX_PORT_ATTEMPTS; i++) {
    const candidate = BASE_PORT + i
    const probe = await probeHealth(candidate)
    if (probe?.ours) {
      port = candidate
      reuse = true
      break
    }
    if (probe === null) {
      port = candidate
      break
    }
    // 端口被其他程序占用，继续找下一个
  }

  const token = randomBytes(24).toString('hex')
  if (reuse) {
    // 复用模式下沿用现有后端（其鉴权状态以它自己的启动参数为准，health 豁免不受影响）
    return { port, token, child: null, stop: async () => undefined }
  }

  const { command, args, cwd } = backendCommand(port)
  const spawnOnce = (): ChildProcess => {
    const proc = spawn(command, args, {
      cwd,
      env: { ...process.env, KATE_API_TOKEN: token },
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe']
    })
    proc.stdout?.on('data', (d) => console.log(`[sidecar] ${String(d).trim()}`))
    proc.stderr?.on('data', (d) => console.error(`[sidecar] ${String(d).trim()}`))
    return proc
  }

  let child = spawnOnce()
  let stopped = false
  let restarts = 0
  // 意外死亡自动复活（上限 3 次防死循环）：后端被外部 kill（如开发期手动
  // 重启 1738）不再连带整个应用退出；同 port 同 token 重拉，renderer 无感
  const onExit = (code: number | null): void => {
    if (stopped) return
    if (++restarts > 3) {
      console.error(`[sidecar] 后端反复退出（code=${code}），放弃自动重启`)
      return
    }
    console.warn(`[sidecar] 后端意外退出 code=${code}，1s 后自动重启（第 ${restarts} 次）`)
    setTimeout(() => {
      if (stopped) return
      child = spawnOnce()
      child.on('exit', onExit)
    }, 1000)
  }
  child.on('exit', onExit)

  // 2) 健康轮询直到就绪（uv 冷启动首次要装环境，给足 60s）
  const deadline = Date.now() + STARTUP_TIMEOUT_MS
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      stopped = true
      throw new Error(`后端进程提前退出（code=${child.exitCode}）`)
    }
    const probe = await probeHealth(port)
    if (probe?.ours) {
      return {
        port,
        token,
        child,
        stop: async () => {
          stopped = true
          await killTree(child.pid ?? -1)
        }
      }
    }
    await sleep(POLL_INTERVAL_MS)
  }
  stopped = true
  await killTree(child.pid ?? -1)
  throw new Error(`后端 ${STARTUP_TIMEOUT_MS / 1000}s 内未就绪（端口 ${port}）`)
}
