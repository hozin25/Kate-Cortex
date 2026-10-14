import { describe, expect, it, vi } from 'vitest'
import { runEnrichLoop } from './importEnrich'
import type { EnrichApiClient, EnrichResponse } from './importEnrich'

function body(overrides: Partial<EnrichResponse>): EnrichResponse {
  return {
    processed: 0,
    remaining: 0,
    done: true,
    enriched: [],
    skipped: [],
    ...overrides
  }
}

const DUP = { entry_id: 'kc_1', title: '旧条目', similarity: 0.95 }

function apiOf(rounds: EnrichResponse[]): EnrichApiClient {
  const queue = [...rounds]
  return {
    post: vi.fn(() => Promise.resolve(queue.shift() ?? body({}))) as EnrichApiClient['post']
  }
}

describe('runEnrichLoop', () => {
  it('循环调用直到 remaining=0，汇总加工/跳过/重复数', async () => {
    const api = apiOf([
      body({ processed: 1, remaining: 2, done: false, enriched: [{ duplicates: [DUP] }] }),
      body({
        processed: 1,
        remaining: 1,
        done: false,
        enriched: [{ duplicates: [DUP] }],
        skipped: ['x：LLM 输出无法解析']
      }),
      body({ processed: 1, remaining: 0 })
    ])

    const result = await runEnrichLoop(api, { limit: 2 })

    expect(vi.mocked(api.post)).toHaveBeenCalledTimes(3)
    expect(vi.mocked(api.post)).toHaveBeenLastCalledWith('/import/enrich', { limit: 2 })
    expect(result.processed).toBe(3)
    expect(result.duplicates).toBe(2)
    expect(result.skipped).toBe(1)
    expect(result.skippedReasons).toEqual(['x：LLM 输出无法解析'])
  })

  it('每轮上报进度：done = total - remaining', async () => {
    const api = apiOf([
      body({ processed: 1, remaining: 2, done: false }),
      body({ processed: 1, remaining: 1, done: false }),
      body({ processed: 1, remaining: 0 })
    ])
    const onProgress = vi.fn()

    await runEnrichLoop(api, { onProgress })

    expect(onProgress).toHaveBeenNthCalledWith(1, { done: 1, total: 3 })
    expect(onProgress).toHaveBeenNthCalledWith(2, { done: 2, total: 3 })
    expect(onProgress).toHaveBeenNthCalledWith(3, { done: 3, total: 3 })
  })

  it('接口抛错时异常上抛且不再继续调用', async () => {
    const post = vi.fn(() => Promise.reject(new Error('未配置 glm 的 API key')))
    const api = { post } as unknown as EnrichApiClient

    await expect(runEnrichLoop(api)).rejects.toThrow('未配置')
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('maxRounds 兜底：反复失败的条目不会死循环', async () => {
    // remaining 永远是 1（坏条目一直留在待选里）
    const stuck = body({ processed: 0, remaining: 1, done: false, skipped: ['x：无法解析'] })
    const post = vi.fn(() => Promise.resolve(stuck))
    const api = { post } as unknown as EnrichApiClient

    const result = await runEnrichLoop(api, { maxRounds: 5 })

    expect(post).toHaveBeenCalledTimes(5)
    expect(result.processed).toBe(0)
    expect(result.skipped).toBe(5)
  })
})
