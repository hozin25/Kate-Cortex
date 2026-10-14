/**
 * 导入条目自动加工循环（IMPORT_ENRICH_PLAN.md §6）。
 *
 * 后端 /import/enrich 是拉取式分批端点：每次加工一小批即返回，前端循环调用
 * 直到 remaining=0。独立成模块便于单测循环与进度语义（不依赖组件）。
 */

export interface EnrichApiClient {
  post: <T>(path: string, body?: unknown) => Promise<T>
}

export interface EnrichProgress {
  done: number // 已加工条数（剩余待加工 = total - done）
  total: number // 启动时的待加工总数
}

export interface EnrichLoopResult {
  processed: number
  skipped: number
  duplicates: number
  skippedReasons: string[]
}

export interface EnrichResponse {
  processed: number
  remaining: number
  done: boolean
  enriched: { duplicates: { entry_id: string; title: string; similarity: number }[] }[]
  skipped: string[]
}

export interface EnrichLoopOptions {
  limit?: number
  /** 轮数兜底：个别条目反复解析失败时会一直留在待选里，防止死循环 */
  maxRounds?: number
  onProgress?: (progress: EnrichProgress) => void
}

export async function runEnrichLoop(
  api: EnrichApiClient,
  options: EnrichLoopOptions = {}
): Promise<EnrichLoopResult> {
  const limit = options.limit ?? 8
  const maxRounds = options.maxRounds ?? 100
  const totals: EnrichLoopResult = {
    processed: 0,
    skipped: 0,
    duplicates: 0,
    skippedReasons: []
  }
  let total = -1

  for (let round = 0; round < maxRounds; round++) {
    const res = await api.post<EnrichResponse>('/import/enrich', { limit })
    if (total < 0) total = res.remaining + res.processed
    totals.processed += res.processed
    totals.skipped += res.skipped.length
    totals.skippedReasons.push(...res.skipped)
    totals.duplicates += res.enriched.reduce((n, item) => n + item.duplicates.length, 0)
    options.onProgress?.({ done: total - res.remaining, total })
    if (res.done) return totals
  }
  return totals
}
