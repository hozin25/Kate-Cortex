import { describe, expect, it, vi } from 'vitest'
import { runConsolidationLoop } from './consolidate'
import type { ConsolidateRunResult, EnrichApiClient } from './consolidate'

function body(overrides: Partial<ConsolidateRunResult>): ConsolidateRunResult {
  return {
    merged: [],
    adjusted: [],
    archived: [],
    conflicts_queued: 0,
    profile_proposals: 0,
    remaining: 0,
    done: true,
    ...overrides
  }
}

describe('runConsolidationLoop', () => {
  it('循环调用直到 done，汇总各阶段计数', async () => {
    const post = vi
      .fn()
      .mockResolvedValueOnce(
        body({
          merged: [
            {
              kept_id: 'a',
              kept_title: ' kept',
              trashed_id: 'b',
              trashed_title: 'drop',
              reason: ''
            }
          ],
          adjusted: [{ entry_id: 'a', title: 't', from: 3, to: 4 }],
          conflicts_queued: 1,
          remaining: 1,
          done: false
        })
      )
      .mockResolvedValueOnce(
        body({ archived: [{ entry_id: 'c', title: 'old' }], profile_proposals: 2 })
      )
    const api = { post } as unknown as EnrichApiClient
    const onRemaining = vi.fn()

    const result = await runConsolidationLoop(api, { onRemaining })

    expect(post).toHaveBeenCalledTimes(2)
    expect(post).toHaveBeenLastCalledWith('/consolidate/run', { limit: 6 })
    expect(onRemaining).toHaveBeenNthCalledWith(1, 1)
    expect(onRemaining).toHaveBeenNthCalledWith(2, 0)
    expect(result).toEqual({
      merged: [
        { kept_id: 'a', kept_title: ' kept', trashed_id: 'b', trashed_title: 'drop', reason: '' }
      ],
      adjusted: 1,
      archived: 1,
      conflicts: 1,
      profileProposals: 2
    })
  })

  it('接口抛错时异常上抛且不再继续调用', async () => {
    const post = vi.fn(() => Promise.reject(new Error('未配置 glm 的 API key')))
    const api = { post } as unknown as EnrichApiClient

    await expect(runConsolidationLoop(api)).rejects.toThrow('未配置')
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('maxRounds 兜底：remaining 一直不为 0 时不会死循环', async () => {
    const stuck = body({ remaining: 2, done: false })
    const post = vi.fn(() => Promise.resolve(stuck))
    const api = { post } as unknown as EnrichApiClient

    await runConsolidationLoop(api, { maxRounds: 4 })

    expect(post).toHaveBeenCalledTimes(4)
  })
})
