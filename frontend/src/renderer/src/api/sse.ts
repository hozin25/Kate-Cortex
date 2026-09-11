import { kateRuntime } from '@renderer/lib/runtime'
import { notifyUnauthorized } from '@renderer/api/client'

const RUNTIME = kateRuntime()
const BASE = import.meta.env.VITE_API_BASE ?? `http://127.0.0.1:${RUNTIME?.apiPort ?? 1738}/api`
const API_TOKEN = RUNTIME?.apiToken ?? import.meta.env.VITE_API_TOKEN

export interface SseHandler {
  onEvent: (event: string, data: Record<string, unknown>) => void
  onError?: (message: string) => void
  onDone?: () => void
}

/** POST + SSE 流读取：解析 `event:`/`data:` 行，AbortController 断开即取消 */
export async function postSse(
  path: string,
  body: unknown,
  handler: SseHandler,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(API_TOKEN ? { 'X-Kate-Token': API_TOKEN } : {})
    },
    body: JSON.stringify(body),
    signal
  })
  if (!resp.ok || !resp.body) {
    if (resp.status === 401) notifyUnauthorized()
    let detail = `请求失败 (${resp.status})`
    try {
      const err = await resp.json()
      if (err?.detail) detail = String(err.detail)
    } catch {
      /* 保留默认消息 */
    }
    handler.onError?.(detail)
    return
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false

  while (!finished) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const parsed = parseBlock(block)
      if (!parsed) continue
      handler.onEvent(parsed.event, parsed.data)
      if (parsed.event === 'done' || parsed.event === 'error') finished = true
    }
  }
  handler.onDone?.()
}

function parseBlock(block: string): { event: string; data: Record<string, unknown> } | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7).trim()
    else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
  }
  if (dataLines.length === 0) return null
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) as Record<string, unknown> }
  } catch {
    return null
  }
}
