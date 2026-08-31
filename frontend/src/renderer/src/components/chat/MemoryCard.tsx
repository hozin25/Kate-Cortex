import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'motion/react'
import { Brain, ExternalLink, Undo2 } from 'lucide-react'
import { cn } from '@renderer/lib/utils'
import type { MemorySavedPayload } from '@renderer/types'

interface MemoryCardProps {
  memory: MemorySavedPayload
  onUndo: () => Promise<void>
}

export function MemoryCard({ memory, onUndo }: MemoryCardProps): React.JSX.Element {
  const [undoing, setUndoing] = useState(false)

  const undo = async (): Promise<void> => {
    if (undoing) return
    setUndoing(true)
    await onUndo()
    setUndoing(false)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.28, ease: [0.21, 1, 0.35, 1] }}
      className="w-full max-w-lg"
    >
      <div className="flex items-center gap-3 rounded-2xl border border-aurora-indigo/15 bg-aurora-indigo/[0.06] px-4 py-2.5">
        <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-aurora-indigo/15 text-aurora-indigo">
          <Brain className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] text-aurora-indigo/90">
            {memory.replaced ? 'Kate 更新了记忆' : 'Kate 已记住'}
          </div>
          <div className="mt-0.5 truncate text-sm text-zinc-200">{memory.title}</div>
          {memory.keywords.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {memory.keywords.map((k) => (
                <span
                  key={k}
                  className="rounded-md border border-white/[0.06] bg-white/[0.04] px-1.5 py-0.5 text-[10px] text-zinc-500"
                >
                  {k}
                </span>
              ))}
            </div>
          )}
        </div>
        <Link
          to={`/entries/${memory.entry_id}`}
          title="查看记忆条目"
          className="shrink-0 rounded-lg p-1.5 text-zinc-500 transition hover:text-zinc-200"
        >
          <ExternalLink className="size-3.5" />
        </Link>
        <button
          onClick={() => void undo()}
          disabled={undoing}
          title="撤销：删除这条记忆"
          className={cn(
            'flex shrink-0 items-center gap-1 rounded-lg border border-white/10 bg-white/[0.04]',
            'px-2.5 py-1.5 text-xs text-zinc-400 transition hover:text-zinc-100 disabled:opacity-50'
          )}
        >
          <Undo2 className="size-3" />
          {undoing ? '撤销中…' : '撤销'}
        </button>
      </div>
    </motion.div>
  )
}
