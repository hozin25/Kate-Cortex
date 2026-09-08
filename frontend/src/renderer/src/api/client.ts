// 后端端口与鉴权 token 由 Electron preload 注入（sidecar 启动时生成）；
// 纯 vite / 测试环境无注入，回落到默认端口、不携带 token；
// Web 构建（Vercel）经 VITE_API_BASE 指向同源 /api 或任意远程后端
const RUNTIME = typeof window !== 'undefined' ? window.api?.kateRuntime : undefined
const BASE = import.meta.env.VITE_API_BASE ?? `http://127.0.0.1:${RUNTIME?.apiPort ?? 1738}/api`
const API_TOKEN = RUNTIME?.apiToken ?? import.meta.env.VITE_API_TOKEN

/** 供 <img> 等无法带请求头的场景：token 走查询参数 */
export function apiUrl(path: string): string {
  if (!API_TOKEN) return `${BASE}${path}`
  const sep = path.includes('?') ? '&' : '?'
  return `${BASE}${path}${sep}api_token=${encodeURIComponent(API_TOKEN)}`
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(API_TOKEN ? { 'X-Kate-Token': API_TOKEN } : {})
    },
    ...init
  })
  if (!resp.ok) {
    let detail = `请求失败 (${resp.status})`
    try {
      const body = await resp.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      /* 非 JSON 错误体，保留默认消息 */
    }
    throw new ApiError(resp.status, detail)
  }
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

export const api = {
  get: <T>(path: string): Promise<T> => request<T>(path),
  post: <T>(path: string, body?: unknown): Promise<T> =>
    request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body)
    }),
  put: <T>(path: string, body: unknown): Promise<T> =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown): Promise<T> =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string): Promise<T> => request<T>(path, { method: 'DELETE' })
}
