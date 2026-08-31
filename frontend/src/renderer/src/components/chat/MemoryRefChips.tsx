import { Link } from 'react-router-dom'
import { Brain } from 'lucide-react'
import type { MemoryRefItem } from '@renderer/types'

export function MemoryRefChips({
  memories
}: {
  memories: MemoryRefItem[]
}): React.JSX.Element | null {
  if (memories.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="flex items-center gap-1 text-[11px] text-zinc-500">
        <Brain className="size-3" />
        想起
      </span>
      {memories.map((m) => (
        <Link
          key={m.entry_id}
          to={`/entries/${m.entry_id}`}
          title={m.content}
          className="flex max-w-48 items-center gap-1 rounded-full border border-aurora-indigo/25 bg-aurora-indigo/10 px-2 py-0.5 text-[11px] text-aurora-indigo transition hover:bg-aurora-indigo/20"
        >
          <Brain className="size-3 shrink-0" />
          <span className="truncate">{m.title}</span>
        </Link>
      ))}
    </div>
  )
}
