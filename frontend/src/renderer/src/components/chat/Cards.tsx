import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'motion/react'
import { BookCheck, ExternalLink, FolderOpen, Sparkles } from 'lucide-react'
import { api } from '@renderer/api/client'
import { toast } from '@renderer/stores/toast'
import { cn } from '@renderer/lib/utils'
import type { CollectionCount, SavedPayload, SuggestPayload } from '@renderer/types'

export function SavedCard({ saved }: { saved: SavedPayload }): React.JSX.Element {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.28, ease: [0.21, 1, 0.35, 1] }}
      className="gradient-ring w-full max-w-lg"
    >
      <div className="gradient-ring-inner flex items-center gap-3 px-4 py-3">
        <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-emerald-400/12 text-emerald-300">
          <BookCheck className="size-4.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-emerald-300/90">
            <span className="font-medium">已存入知识库</span>
          </div>
          <div className="mt-0.5 truncate text-sm text-zinc-200">{saved.title}</div>
          {saved.collections.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {saved.collections.map((c) => (
                <span
                  key={c}
                  className="flex items-center gap-0.5 rounded-md border border-aurora-indigo/20 bg-aurora-indigo/10 px-1.5 py-0.5 text-[10px] text-aurora-indigo/90"
                >
                  <FolderOpen className="size-2.5" />
                  {c}
                </span>
              ))}
            </div>
          )}
        </div>
        <Link
          to={`/entries/${saved.entry_id}`}
          className="flex shrink-0 items-center gap-1 rounded-lg border border-white/10 bg-white/[0.05] px-2.5 py-1.5 text-xs text-zinc-300 transition hover:border-emerald-400/30 hover:text-emerald-200"
        >
          查看
          <ExternalLink className="size-3" />
        </Link>
      </div>
    </motion.div>
  )
}

interface SuggestCardProps {
  suggest: SuggestPayload
  conversationId: string
  onDismiss: () => void
}

export function SuggestCard({
  suggest,
  conversationId,
  onDismiss
}: SuggestCardProps): React.JSX.Element {
  const [confirming, setConfirming] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [entryId, setEntryId] = useState<string | null>(null)
  const [collections, setCollections] = useState<CollectionCount[]>([])
  const [selected, setSelected] = useState<string[]>(suggest.collections)

  useEffect(() => {
    api
      .get<CollectionCount[]>('/collections')
      .then(setCollections)
      .catch(() => undefined)
  }, [])

  const toggle = (name: string): void => {
    setSelected((prev) => (prev.includes(name) ? prev.filter((c) => c !== name) : [...prev, name]))
  }

  const confirm = async (): Promise<void> => {
    if (confirming) return
    setConfirming(true)
    try {
      const entry = await api.post<{ id: string }>('/entries', {
        title: suggest.title,
        collections: selected,
        content: suggest.preview,
        source: 'chat',
        conversation_id: conversationId
      })
      setEntryId(entry.id)
      setConfirmed(true)
      toast.success(`已保存《${suggest.title}》`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setConfirming(false)
    }
  }

  if (confirmed) {
    return (
      <SavedCard
        saved={{
          entry_id: entryId ?? '',
          slug: '',
          title: suggest.title,
          collections: selected
        }}
      />
    )
  }

  const selectable = Array.from(
    new Set([...collections.map((c) => c.name), ...suggest.collections])
  )

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.28, ease: [0.21, 1, 0.35, 1] }}
      className="glass-deep w-full max-w-lg rounded-2xl p-4"
    >
      <div className="flex items-center gap-2 text-xs text-amber-300/90">
        <Sparkles className="size-3.5" />
        <span className="font-medium">Kate 觉得这条值得留下</span>
      </div>
      <div className="mt-2 text-sm font-medium text-zinc-100">{suggest.title}</div>
      <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-[13px] leading-6 text-zinc-400">
        {suggest.preview}
      </p>
      {selectable.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] text-zinc-600">收入合集</span>
          {selectable.map((name) => {
            const active = selected.includes(name)
            const suggested = suggest.collections.includes(name)
            return (
              <button
                key={name}
                onClick={() => toggle(name)}
                className={cn(
                  'rounded-full border px-2 py-0.5 text-[11px] transition',
                  active
                    ? 'border-aurora-indigo/40 bg-aurora-indigo/15 text-aurora-indigo'
                    : 'border-white/[0.08] bg-white/[0.03] text-zinc-500 hover:text-zinc-300'
                )}
              >
                {name}
                {suggested && (
                  <span className="ml-1 text-[9px] opacity-70" title="Kate 建议">
                    ★
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}
      <div className="mt-3 flex gap-2">
        <button
          onClick={() => void confirm()}
          disabled={confirming}
          className="rounded-lg border border-emerald-400/30 bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-emerald-200 transition hover:bg-emerald-500/25 disabled:opacity-50"
        >
          {confirming ? '保存中…' : '存入知识库'}
        </button>
        <button
          onClick={onDismiss}
          disabled={confirming}
          className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-zinc-400 transition hover:text-zinc-200 disabled:opacity-50"
        >
          忽略
        </button>
      </div>
    </motion.div>
  )
}
