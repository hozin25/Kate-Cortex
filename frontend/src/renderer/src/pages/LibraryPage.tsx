import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'motion/react'
import { Library, Plus, Search, Tag } from 'lucide-react'
import { TypeBadge, Spinner } from '@renderer/components/common/Badges'
import { EmptyState } from '@renderer/components/common/EmptyState'
import { useLibraryStore } from '@renderer/stores/library'
import { toast } from '@renderer/stores/toast'
import { cn, formatTime, TYPE_LABELS } from '@renderer/lib/utils'

export function LibraryPage(): React.JSX.Element {
  const store = useLibraryStore()
  const { items, total, tags, typeFilter, tagFilter, query, loading } = store
  const [searchDraft, setSearchDraft] = useState(query)

  useEffect(() => {
    void store
      .load()
      .catch((err) => toast.error(err instanceof Error ? err.message : '知识库加载失败'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const t = setTimeout(() => {
      if (searchDraft !== query) store.setQuery(searchDraft)
    }, 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft])

  return (
    <div className="flex h-full min-h-0 flex-col px-8 py-6">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-lg text-zinc-100">
          知识库 <span className="ml-1 text-sm text-zinc-500">{total} 条</span>
        </h1>
        <Link
          to="/entries/new"
          className="flex items-center gap-1.5 rounded-xl border border-aurora-indigo/30 bg-gradient-to-r from-aurora-indigo/20 to-aurora-violet/15 px-3 py-1.5 text-[13px] text-zinc-100 transition hover:brightness-125"
        >
          <Plus className="size-3.5" />
          新条目
        </Link>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <div className="glass flex min-w-56 flex-1 items-center gap-2 rounded-xl px-3 py-2">
          <Search className="size-4 shrink-0 text-zinc-500" />
          <input
            value={searchDraft}
            onChange={(e) => setSearchDraft(e.target.value)}
            placeholder="全文搜索标题、正文、标签…"
            className="w-full bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
          />
          {loading && <Spinner className="size-3.5" />}
        </div>
        <div className="flex items-center gap-1">
          <FilterChip
            active={typeFilter === null}
            onClick={() => store.setTypeFilter(null)}
            label="全部"
          />
          {Object.entries(TYPE_LABELS).map(([type, label]) => (
            <FilterChip
              key={type}
              active={typeFilter === type}
              onClick={() => store.setTypeFilter(type)}
              label={label}
            />
          ))}
        </div>
      </div>

      {tags.length > 0 && (
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <Tag className="size-3 text-zinc-600" />
          {tags.map((t) => (
            <button
              key={t.name}
              onClick={() => store.setTagFilter(tagFilter === t.name ? null : t.name)}
              className={cn(
                'rounded-full border px-2 py-0.5 text-[11px] transition',
                tagFilter === t.name
                  ? 'border-aurora-cyan/40 bg-aurora-cyan/15 text-aurora-cyan'
                  : 'border-white/[0.08] bg-white/[0.03] text-zinc-500 hover:text-zinc-300'
              )}
            >
              #{t.name}
              <span className="ml-1 text-[9px] opacity-60">{t.count}</span>
            </button>
          ))}
        </div>
      )}

      <div className="mt-4 min-h-0 flex-1 overflow-y-auto pr-1">
        {items.length === 0 && !loading ? (
          <EmptyState
            icon={<Library className="size-6" />}
            title={query || typeFilter || tagFilter ? '没有匹配的条目' : '知识库还是空的'}
            hint={
              query || typeFilter || tagFilter
                ? '换个关键词或清除过滤条件试试'
                : '在对话里让 Kate「记一下」，或点击右上角手动新建'
            }
          />
        ) : (
          <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2 xl:grid-cols-3">
            {items.map((entry, i) => (
              <motion.div
                key={entry.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  delay: Math.min(i * 0.03, 0.3),
                  duration: 0.3,
                  ease: [0.21, 1, 0.35, 1]
                }}
              >
                <Link
                  to={`/entries/${entry.id}`}
                  className="glass block h-full rounded-2xl p-4 transition hover:border-aurora-indigo/30 hover:bg-white/[0.07]"
                >
                  <div className="flex items-center gap-2">
                    <TypeBadge type={entry.type} />
                    {entry.source === 'chat' && (
                      <span className="rounded-full bg-aurora-violet/15 px-1.5 py-0.5 text-[10px] text-aurora-violet">
                        对话沉淀
                      </span>
                    )}
                    <span className="ml-auto text-[10px] text-zinc-600">
                      {formatTime(entry.updated_at)}
                    </span>
                  </div>
                  <h3 className="mt-2 line-clamp-2 text-sm font-medium leading-6 text-zinc-100">
                    {entry.title}
                  </h3>
                  {entry.tags.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {entry.tags.slice(0, 4).map((t) => (
                        <span
                          key={t}
                          className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-zinc-500"
                        >
                          #{t}
                        </span>
                      ))}
                    </div>
                  )}
                </Link>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

interface FilterChipProps {
  active: boolean
  label: string
  onClick: () => void
}

function FilterChip({ active, label, onClick }: FilterChipProps): React.JSX.Element {
  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-lg border px-2.5 py-1.5 text-xs transition',
        active
          ? 'border-aurora-indigo/40 bg-aurora-indigo/15 text-zinc-100'
          : 'border-white/[0.08] bg-white/[0.03] text-zinc-500 hover:text-zinc-300'
      )}
    >
      {label}
    </button>
  )
}
