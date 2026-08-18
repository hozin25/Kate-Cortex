import { Link } from 'react-router-dom'
import { BookOpen, Library } from 'lucide-react'
import type { Citation } from '@renderer/types'

export function CitationChips({ citations }: { citations: Citation[] }): React.JSX.Element | null {
  if (citations.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="flex items-center gap-1 text-[11px] text-zinc-500">
        <Library className="size-3" />
        引用
      </span>
      {citations.map((c) => (
        <Link
          key={c.id}
          to={`/entries/${c.id}`}
          title={c.title}
          className="flex max-w-48 items-center gap-1 rounded-full border border-aurora-cyan/25 bg-aurora-cyan/10 px-2 py-0.5 text-[11px] text-aurora-cyan transition hover:bg-aurora-cyan/20"
        >
          <BookOpen className="size-3 shrink-0" />
          <span className="truncate">{c.title}</span>
        </Link>
      ))}
    </div>
  )
}
