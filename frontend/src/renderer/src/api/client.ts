const BASE = 'http://127.0.0.1:1738/api'

// 本地 API 鉴权 token：Electron sidecar 就绪后由 preload 注入
// window.__KATE_API_TOKEN__（阶段 5）；dev 手动起后端（无 KATE_API_TOKEN）时为空
const API_TOKEN: string | undefined = (globalThis as { __KATE_API_TOKEN__?: string })
  .__KATE_API_TOKEN__

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
