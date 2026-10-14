import { useState } from 'react'
import { Check, ChevronDown, ChevronUp, Sparkles, Undo2, X } from 'lucide-react'
import { GlassPanel } from '@renderer/components/common/Glass'
import { Spinner } from '@renderer/components/common/Badges'
import { api } from '@renderer/api/client'
import { toast } from '@renderer/stores/toast'
import { runConsolidationLoop } from '@renderer/lib/consolidate'
import type { ConsolidationProposal, ConsolidationStatus, ProposalEntry } from '@renderer/types'

/**
 * 记忆整理面板（CONSOLIDATE_PLAN.md §6）。默认折叠、展开才拉状态——
 * 不在页面挂载时自动请求，避免后台产生 LLM 费用。
 */
export function ConsolidationPanel({
  onChanged
}: {
  onChanged: () => Promise<void>
}): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState<ConsolidationStatus | null>(null)
  const [loadingStatus, setLoadingStatus] = useState(false)
  const [running, setRunning] = useState(false)
  const [remaining, setRemaining] = useState<number | null>(null)

  const expand = async (): Promise<void> => {
    setOpen((v) => !v)
    if (status || loadingStatus) return
    setLoadingStatus(true)
    try {
      setStatus(await api.get<ConsolidationStatus>('/consolidate/status'))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '整理状态加载失败')
    } finally {
      setLoadingStatus(false)
    }
  }

  const run = async (): Promise<void> => {
    setRunning(true)
    try {
      const result = await runConsolidationLoop(api, { onRemaining: setRemaining })
      const parts = [`合并 ${result.merged.length}`, `调整重要度 ${result.adjusted}`]
      if (result.archived > 0) parts.push(`归档 ${result.archived}`)
      if (result.conflicts > 0) parts.push(`待确认冲突 ${result.conflicts}`)
      if (result.profileProposals > 0) parts.push(`画像提案 ${result.profileProposals}`)
      toast.success(`整理完成：${parts.join('，')}`)
      setStatus(await api.get<ConsolidationStatus>('/consolidate/status'))
      await onChanged()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '整理失败')
    } finally {
      setRunning(false)
      setRemaining(null)
    }
  }

  const undo = async (entryId: string, title: string): Promise<void> => {
    try {
      await api.post(`/consolidate/undo/${entryId}`)
      toast.success(`已恢复「${title}」（合并产物可在知识库中手动删除）`)
      setStatus(await api.get<ConsolidationStatus>('/consolidate/status'))
      await onChanged()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '恢复失败')
    }
  }

  const decide = async (proposal: ConsolidationProposal, keep?: 'a' | 'b'): Promise<void> => {
    try {
      const method = keep
        ? api.post(`/consolidate/proposals/${proposal.id}/accept`, { keep })
        : api.delete(`/consolidate/proposals/${proposal.id}`)
      await method
      toast.success(keep ? '已按选择处理' : '已忽略该提案')
      setStatus(await api.get<ConsolidationStatus>('/consolidate/status'))
      await onChanged()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作失败')
    }
  }

  const report = status?.report

  return (
    <GlassPanel className="p-4">
      <button
        onClick={() => void expand()}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <span className="flex items-center gap-2 text-[13px] text-zinc-200">
          <Sparkles className="size-3.5 text-aurora-violet" />
          记忆整理
          {status && status.proposals.length > 0 && (
            <span className="rounded-full border border-amber-300/30 bg-amber-300/10 px-2 py-0.5 text-[10px] text-amber-200">
              {status.proposals.length} 条待确认
            </span>
          )}
        </span>
        {open ? (
          <ChevronUp className="size-4 text-zinc-500" />
        ) : (
          <ChevronDown className="size-4 text-zinc-500" />
        )}
      </button>

      {open && (
        <div className="mt-3 space-y-3">
          <p className="text-[11px] leading-4 text-zinc-500">
            合并重复记忆（可撤销）、按召回情况升降重要度、归档久未想起的低重要度记忆；
            冲突与画像改动只生成提案，由你确认。只处理「记忆/个人信息」，知识库文档不碰。
          </p>
          <div className="flex items-center justify-between gap-2">
            <div className="text-[11px] leading-4 text-zinc-500">
              {loadingStatus ? (
                '读取状态中…'
              ) : status ? (
                <>
                  上次整理：
                  {status.consolidated_at
                    ? status.consolidated_at.slice(0, 16).replace('T', ' ')
                    : '从未整理'}
                  {status.candidates > 0 && ` · 约 ${status.candidates} 对疑似重复`}
                  {!status.vector_available && ' · 未启用向量（跳过重复合并）'}
                </>
              ) : (
                '—'
              )}
            </div>
            <button
              onClick={() => void run()}
              disabled={
                running || (status !== null && !status.vector_available && status.candidates === 0)
              }
              className="flex shrink-0 items-center gap-1 rounded-xl border border-aurora-violet/30 bg-aurora-violet/15 px-3 py-1.5 text-xs text-zinc-200 transition hover:brightness-125 disabled:opacity-40"
            >
              {running ? <Spinner className="size-3.5" /> : <Sparkles className="size-3.5" />}
              {running
                ? `整理中${remaining !== null && remaining > 0 ? `（剩余 ${remaining} 对）` : '…'}`
                : '整理记忆'}
            </button>
          </div>

          {report && report.merged.length > 0 && (
            <div className="space-y-1.5">
              <div className="text-[11px] text-zinc-400">
                上次合并（{report.ran_at.slice(0, 16).replace('T', ' ')}）
              </div>
              {report.merged.map((m) => (
                <div
                  key={m.trashed_id}
                  className="flex items-center justify-between gap-2 rounded-xl bg-white/[0.04] px-3 py-2 text-[11px] leading-4 text-zinc-400"
                >
                  <span className="min-w-0 truncate">
                    《{m.trashed_title}》已并入《{m.kept_title}》{m.reason ? `（${m.reason}）` : ''}
                  </span>
                  <button
                    onClick={() => void undo(m.trashed_id, m.trashed_title)}
                    className="flex shrink-0 items-center gap-1 rounded-lg border border-white/10 px-2 py-1 text-zinc-300 transition hover:text-zinc-100"
                  >
                    <Undo2 className="size-3" />
                    撤销
                  </button>
                </div>
              ))}
            </div>
          )}

          {status && status.proposals.length > 0 && (
            <div className="space-y-2">
              {status.proposals.map((p) => (
                <ProposalCard key={p.id} proposal={p} onDecide={decide} />
              ))}
            </div>
          )}
        </div>
      )}
    </GlassPanel>
  )
}

function ProposalCard({
  proposal,
  onDecide
}: {
  proposal: ConsolidationProposal
  onDecide: (proposal: ConsolidationProposal, keep?: 'a' | 'b') => Promise<void>
}): React.JSX.Element {
  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.03] p-3">
      {proposal.kind === 'conflict' && proposal.a && proposal.b && (
        <ConflictBody a={proposal.a} b={proposal.b} reason={proposal.reason} />
      )}
      {proposal.kind === 'profile_update' && (
        <div>
          <div className="text-[12px] text-zinc-200">
            档案更新建议：{proposal.title || '（保持原标题）'}
          </div>
          <p className="mt-1 whitespace-pre-wrap text-[11px] leading-4 text-zinc-400">
            {proposal.content}
          </p>
        </div>
      )}
      {proposal.kind === 'profile_create' && (
        <div>
          <div className="text-[12px] text-zinc-200">新档案条目建议：{proposal.title}</div>
          <p className="mt-1 whitespace-pre-wrap text-[11px] leading-4 text-zinc-400">
            {proposal.content}
          </p>
        </div>
      )}
      {proposal.reason && <p className="mt-1 text-[11px] text-zinc-500">依据：{proposal.reason}</p>}
      <div className="mt-2 flex justify-end gap-2">
        {proposal.kind === 'conflict' && (
          <>
            <DecideButton label="保留较新" onClick={() => onDecide(proposal, 'b')} />
            <DecideButton label="保留较旧" onClick={() => onDecide(proposal, 'a')} />
          </>
        )}
        {proposal.kind.startsWith('profile') && (
          <DecideButton label="采纳" primary onClick={() => onDecide(proposal)} />
        )}
        <DecideButton label="忽略" onClick={() => onDecide(proposal)} />
      </div>
    </div>
  )
}

function ConflictBody({
  a,
  b,
  reason
}: {
  a: ProposalEntry
  b: ProposalEntry
  reason: string
}): React.JSX.Element {
  return (
    <div>
      <div className="text-[12px] text-zinc-200">两条记忆相互冲突：</div>
      <div className="mt-1 grid gap-1.5 sm:grid-cols-2">
        {[a, b].map((side, index) => (
          <div key={side.id} className="rounded-lg bg-white/[0.04] p-2">
            <div className="text-[11px] text-zinc-300">
              {index === 0 ? '较旧' : '较新'} · {side.created_at.slice(0, 10)}
            </div>
            <div className="mt-0.5 text-[12px] text-zinc-200">{side.title}</div>
            <p className="mt-0.5 line-clamp-3 text-[11px] leading-4 text-zinc-500">
              {side.content}
            </p>
          </div>
        ))}
      </div>
      {reason && <p className="mt-1 text-[11px] text-zinc-500">{reason}</p>}
    </div>
  )
}

function DecideButton({
  label,
  onClick,
  primary = false
}: {
  label: string
  onClick: () => void
  primary?: boolean
}): React.JSX.Element {
  return (
    <button
      onClick={() => void onClick()}
      className={
        primary
          ? 'flex items-center gap-1 rounded-lg border border-aurora-cyan/25 bg-aurora-cyan/10 px-2.5 py-1 text-[11px] text-aurora-cyan transition hover:bg-aurora-cyan/20'
          : 'flex items-center gap-1 rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-zinc-300 transition hover:text-zinc-100'
      }
    >
      {primary ? <Check className="size-3" /> : <X className="size-3" />}
      {label}
    </button>
  )
}
