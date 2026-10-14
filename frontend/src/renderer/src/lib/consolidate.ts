/**
 * 记忆巩固循环（CONSOLIDATE_PLAN.md §6）：拉取式分批整理，循环调用
 * /consolidate/run 直到 done。与 importEnrich 同款模式。
 */

export interface EnrichApiClient {
  post: <T>(path: string, body?: unknown) => Promise<T>
}

export interface ConsolidateAction {
  entry_id?: string
  kept_id?: string
  kept_title?: string
  trashed_id?: string
  trashed_title?: string
  title?: string
  from?: number
  to?: number
  reason?: string
}

export interface ConsolidateRunResult {
  merged: ConsolidateAction[]
  adjusted: ConsolidateAction[]
  archived: ConsolidateAction[]
  conflicts_queued: number
  profile_proposals: number
  remaining: number
  done: boolean
}

export interface ConsolidateLoopOptions {
  limit?: number
  maxRounds?: number
  onRemaining?: (remaining: number) => void
}

export interface ConsolidateLoopResult {
  merged: ConsolidateAction[]
  adjusted: number
  archived: number
  conflicts: number
  profileProposals: number
}

export async function runConsolidationLoop(
  api: EnrichApiClient,
  options: ConsolidateLoopOptions = {}
): Promise<ConsolidateLoopResult> {
  const limit = options.limit ?? 6
  const maxRounds = options.maxRounds ?? 50
  const totals: ConsolidateLoopResult = {
    merged: [],
    adjusted: 0,
    archived: 0,
    conflicts: 0,
    profileProposals: 0
  }

  for (let round = 0; round < maxRounds; round++) {
    const res = await api.post<ConsolidateRunResult>('/consolidate/run', { limit })
    totals.merged.push(...res.merged)
    totals.adjusted += res.adjusted.length
    totals.archived += res.archived.length
    totals.conflicts += res.conflicts_queued
    totals.profileProposals += res.profile_proposals
    options.onRemaining?.(res.remaining)
    if (res.done) return totals
  }
  return totals
}
