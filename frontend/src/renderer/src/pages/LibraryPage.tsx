import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { motion } from 'motion/react'
import { FolderOpen, Library, List, Move3d, Pencil, Plus, Search, Trash2, X } from 'lucide-react'
import { Spinner } from '@renderer/components/common/Badges'
import { EmptyState } from '@renderer/components/common/EmptyState'
import { VectorGraph } from '@renderer/components/library/VectorGraph'
import { useLibraryStore } from '@renderer/stores/library'
import { toast } from '@renderer/stores/toast'
import { cn, formatTime } from '@renderer/lib/utils'

type LibraryView = 'list' | 'graph'

export function LibraryPage(): React.JSX.Element {
  const store = useLibraryStore()
  const { items, total, collections, collectionFilter, query, loading } = store
  const searchRef = useRef<HTMLInputElement>(null)
  const focusSearchTick = useLibraryStore((s) => s.focusSearchTick)
  const [searchParams, setSearchParams] = useSearchParams()
  const view: LibraryView = searchParams.get('view') === 'graph' ? 'graph' : 'list'
  const [searchDraft, setSearchDraft] = useState(query)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [renaming, setRenaming] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')

  const setView = (next: LibraryView): void => {
    const params = new URLSearchParams(searchParams)
    if (next === 'graph') params.set('view', 'graph')
    else params.delete('view')
    setSearchParams(params)
  }

  useEffect(() => {
    store.setCollectionFilter(searchParams.get('collection'))
    void store
      .load()
      .catch((err) => toast.error(err instanceof Error ? err.message : '知识库加载失败'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  // Ctrl+K 聚焦信号（App.tsx GlobalShortcuts 触发）
  useEffect(() => {
    if (focusSearchTick > 0) {
      searchRef.current?.focus()
      searchRef.current?.select()
      useLibraryStore.setState({ focusSearchTick: 0 })
    }
  }, [focusSearchTick])

  useEffect(() => {
    const t = setTimeout(() => {
      if (searchDraft !== query) store.setQuery(searchDraft)
    }, 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft])

  const handleCreate = async (): Promise<void> => {
    const name = newName.trim()
    if (!name) {
      setCreating(false)
      return
    }
    try {
      await store.createCollection(name)
      toast.success(`已创建合集「${name}」`)
      setNewName('')
      setCreating(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '创建失败')
    }
  }

  const handleRename = async (oldName: string): Promise<void> => {
    const name = renameDraft.trim()
    setRenaming(null)
    if (!name || name === oldName) return
    try {
      await store.renameCollection(oldName, name)
      toast.success(`已重命名为「${name}」`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '重命名失败')
    }
  }

  const handleDelete = async (name: string): Promise<void> => {
    if (!window.confirm(`删除合集「${name}」？合集内的条目会保留，仅移出合集。`)) return
    try {
      await store.deleteCollection(name)
      toast.info(`已删除合集「${name}」`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  const hasFilter = Boolean(query || collectionFilter)

  return (
    <div className="flex h-full min-h-0 flex-col px-4 py-4 sm:px-8 sm:py-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-display text-lg text-zinc-100">
          知识库 <span className="ml-1 text-sm text-zinc-500">{total} 条</span>
        </h1>
        <div className="flex items-center gap-3">
          <Link
            to="/trash"
            className="grid size-8 place-items-center rounded-xl border border-white/[0.06] bg-white/[0.03] text-zinc-400 transition hover:text-zinc-200"
            title="回收站"
          >
            <Trash2 className="size-4" />
          </Link>
          <div className="flex items-center gap-1 rounded-xl border border-white/[0.06] bg-white/[0.03] p-1">
            <ViewTab
              active={view === 'list'}
              onClick={() => setView('list')}
              icon={<List className="size-3.5" />}
              label="列表"
            />
            <ViewTab
              active={view === 'graph'}
              onClick={() => setView('graph')}
              icon={<Move3d className="size-3.5" />}
              label="立体"
            />
          </div>
          <Link
            to="/entries/new"
            className="flex items-center gap-1.5 rounded-xl border border-aurora-indigo/30 bg-gradient-to-r from-aurora-indigo/20 to-aurora-violet/15 px-3 py-1.5 text-[13px] text-zinc-100 transition hover:brightness-125"
          >
            <Plus className="size-3.5" />
            新条目
          </Link>
        </div>
      </div>

      {view === 'graph' ? (
        <div className="mt-4 min-h-0 flex-1">
          <VectorGraph />
        </div>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <div className="glass flex min-w-0 flex-1 items-center gap-2 rounded-xl px-3 py-2 sm:min-w-56">
              <Search className="size-4 shrink-0 text-zinc-500" />
              <input
                ref={searchRef}
                value={searchDraft}
                onChange={(e) => setSearchDraft(e.target.value)}
                placeholder="全文搜索标题、正文…"
                className="w-full bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
              />
              {loading && <Spinner className="size-3.5" />}
            </div>
            <div className="flex flex-wrap items-center gap-1">
              <FilterChip
                active={collectionFilter === null}
                onClick={() => store.setCollectionFilter(null)}
                label="全部"
              />
              {collections.map((c) =>
                renaming === c.name ? (
                  <input
                    key={c.name}
                    autoFocus
                    value={renameDraft}
                    onChange={(e) => setRenameDraft(e.target.value)}
                    onBlur={() => void handleRename(c.name)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void handleRename(c.name)
                      if (e.key === 'Escape') setRenaming(null)
                    }}
                    className="w-24 rounded-lg border border-aurora-indigo/40 bg-white/[0.06] px-2 py-1.5 text-xs text-zinc-100 outline-none"
                  />
                ) : (
                  <CollectionChip
                    key={c.name}
                    name={c.name}
                    count={c.count}
                    active={collectionFilter === c.name}
                    onClick={() =>
                      store.setCollectionFilter(collectionFilter === c.name ? null : c.name)
                    }
                    onRenameStart={() => {
                      setRenaming(c.name)
                      setRenameDraft(c.name)
                    }}
                    onDelete={() => void handleDelete(c.name)}
                  />
                )
              )}
              {creating ? (
                <input
                  autoFocus
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onBlur={() => void handleCreate()}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void handleCreate()
                    if (e.key === 'Escape') setCreating(false)
                  }}
                  placeholder="合集名称"
                  className="w-24 rounded-lg border border-aurora-indigo/40 bg-white/[0.06] px-2 py-1.5 text-xs text-zinc-100 outline-none placeholder:text-zinc-600"
                />
              ) : (
                <button
                  onClick={() => setCreating(true)}
                  title="新建合集"
                  className="flex items-center gap-1 rounded-lg border border-dashed border-white/15 px-2 py-1.5 text-xs text-zinc-500 transition hover:border-aurora-indigo/40 hover:text-zinc-300"
                >
                  <Plus className="size-3" />
                  合集
                </button>
              )}
            </div>
          </div>

          <div className="mt-4 min-h-0 flex-1 overflow-y-auto pr-1">
            {items.length === 0 && !loading ? (
              <EmptyState
                icon={<Library className="size-6" />}
                title={hasFilter ? '没有匹配的条目' : '知识库还是空的'}
                hint={
                  hasFilter
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
                      {entry.collections.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {entry.collections.map((c) => (
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
                    </Link>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

interface ViewTabProps {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}

function ViewTab({ active, onClick, icon, label }: ViewTabProps): React.JSX.Element {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs transition',
        active
          ? 'bg-aurora-indigo/20 text-zinc-100 shadow-[inset_0_0_0_1px] shadow-aurora-indigo/25'
          : 'text-zinc-500 hover:text-zinc-300'
      )}
    >
      {icon}
      {label}
    </button>
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

interface CollectionChipProps {
  name: string
  count: number
  active: boolean
  onClick: () => void
  onRenameStart: () => void
  onDelete: () => void
}

function CollectionChip({
  name,
  count,
  active,
  onClick,
  onRenameStart,
  onDelete
}: CollectionChipProps): React.JSX.Element {
  return (
    <span
      className={cn(
        'group relative inline-flex items-center rounded-lg border py-1.5 pl-2.5 pr-2 text-xs transition',
        active
          ? 'border-aurora-indigo/40 bg-aurora-indigo/15 text-zinc-100'
          : 'border-white/[0.08] bg-white/[0.03] text-zinc-500 hover:text-zinc-300'
      )}
    >
      <button onClick={onClick}>
        {name}
        <span className="ml-1 text-[9px] opacity-60">{count}</span>
      </button>
      <span className="ml-1 hidden items-center gap-0.5 group-hover:inline-flex">
        <button
          onClick={onRenameStart}
          title="重命名"
          className="text-zinc-600 transition hover:text-zinc-200"
        >
          <Pencil className="size-3" />
        </button>
        <button
          onClick={onDelete}
          title="删除合集"
          className="text-zinc-600 transition hover:text-rose-300"
        >
          <X className="size-3.5" />
        </button>
      </span>
    </span>
  )
}
