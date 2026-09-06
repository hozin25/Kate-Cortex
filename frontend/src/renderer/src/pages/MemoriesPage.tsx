import { useCallback, useEffect, useMemo, useState } from 'react'
import { Brain, Check, Pencil, Search, Star, Trash2, X } from 'lucide-react'
import { GlassPanel } from '@renderer/components/common/Glass'
import { Spinner } from '@renderer/components/common/Badges'
import { EmptyState } from '@renderer/components/common/EmptyState'
import { api } from '@renderer/api/client'
import { toast } from '@renderer/stores/toast'
import { cn } from '@renderer/lib/utils'
import type { Entry, EntrySummary } from '@renderer/types'

const MEMORY_COLLECTION = '记忆'
const LIST_LIMIT = 500 // 与后端 memory.LIST_LIMIT 对齐（个人规模上限）

export function MemoriesPage(): React.JSX.Element {
  const [memories, setMemories] = useState<EntrySummary[] | null>(null)
  const [query, setQuery] = useState('')

  const load = useCallback((): Promise<void> => {
    return api
      .get<{ items: EntrySummary[]; total: number }>(
        `/entries?collection=${encodeURIComponent(MEMORY_COLLECTION)}&limit=${LIST_LIMIT}`
      )
      .then((result) => {
        // 与常驻注入同序：(importance, created_at) 降序——越靠前越常被 Kate 想起
        const sorted = [...result.items].sort(
          (a, b) =>
            (b.importance ?? 3) - (a.importance ?? 3) || b.created_at.localeCompare(a.created_at)
        )
        setMemories(sorted)
      })
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : '记忆加载失败')
        setMemories([])
      })
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const filtered = useMemo(() => {
    if (!memories) return null
    const q = query.trim().toLowerCase()
    if (!q) return memories
    return memories.filter(
      (m) =>
        m.title.toLowerCase().includes(q) || m.keywords.some((k) => k.toLowerCase().includes(q))
    )
  }, [memories, query])

  return (
    <div className="h-full overflow-y-auto px-8 py-6">
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-lg text-zinc-100">记忆</h1>
            <p className="mt-1 text-xs leading-5 text-zinc-500">
              Kate
              在对话中自动记住的关于你的事实。重要度越高越常被想起；过时的记忆可直接编辑或删除，
              删除后移入 vault/.trash 保留。
            </p>
          </div>
          <div className="relative w-44 shrink-0">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-zinc-600" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索标题 / 关键词"
              className="glass-deep w-full rounded-xl py-1.5 pl-8 pr-3 text-[13px] text-zinc-200 outline-none placeholder:text-zinc-600"
            />
          </div>
        </div>

        {filtered === null ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-6 text-zinc-500" />
          </div>
        ) : filtered.length === 0 ? (
          memories?.length === 0 ? (
            <EmptyState
              icon={<Brain className="size-7" />}
              title="还没有记忆"
              hint="开启自动记忆后，Kate 会在对话中自动记住关于你的重要事实（健康、计划、偏好），并在此集中管理。"
            />
          ) : (
            <EmptyState
              icon={<Search className="size-7" />}
              title="没有匹配的记忆"
              hint="换个关键词试试。"
            />
          )
        ) : (
          <div className="flex flex-col gap-2.5">
            {filtered.map((m) => (
              <MemoryCard key={m.id} memory={m} onChanged={load} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

interface MemoryCardProps {
  memory: EntrySummary
  onChanged: () => Promise<void>
}

function MemoryCard({ memory, onChanged }: MemoryCardProps): React.JSX.Element {
  const [detail, setDetail] = useState<Entry | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({ title: '', content: '', keywords: '', importance: 3 })
  const [saving, setSaving] = useState(false)

  const expand = async (): Promise<Entry | null> => {
    if (detail) return detail
    if (loadingDetail) return null
    setLoadingDetail(true)
    try {
      const entry = await api.get<Entry>(`/entries/${memory.id}`)
      setDetail(entry)
      return entry
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '读取记忆失败')
      return null
    } finally {
      setLoadingDetail(false)
    }
  }

  const startEdit = (entry: Entry): void => {
    setDraft({
      title: entry.title,
      content: entry.content,
      keywords: entry.keywords.join('，'),
      importance: entry.importance ?? 3
    })
    setEditing(true)
  }

  const save = async (): Promise<void> => {
    setSaving(true)
    try {
      const keywords = draft.keywords
        .split(/[,，]/)
        .map((k) => k.trim())
        .filter(Boolean)
      await api.put(`/entries/${memory.id}`, {
        title: draft.title.trim() || memory.title,
        content: draft.content,
        keywords,
        importance: draft.importance
      })
      setEditing(false)
      await onChanged()
      toast.success('记忆已更新')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (): Promise<void> => {
    if (!window.confirm(`删除记忆「${memory.title}」？`)) return
    try {
      await api.delete(`/entries/${memory.id}`)
      await onChanged()
      toast.success('记忆已删除（vault/.trash 内保留）')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  if (editing) {
    return (
      <GlassPanel className="flex flex-col gap-2.5 p-4">
        <input
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          placeholder="标题"
          className="glass-deep rounded-xl px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
        />
        <textarea
          value={draft.content}
          onChange={(e) => setDraft({ ...draft, content: e.target.value })}
          rows={3}
          placeholder="记忆内容（一条记忆一个原子事实）"
          className="glass-deep resize-none rounded-xl px-3 py-2 text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-600"
        />
        <div className="flex items-center gap-2">
          <input
            value={draft.keywords}
            onChange={(e) => setDraft({ ...draft, keywords: e.target.value })}
            placeholder="场景关键词（逗号分隔，3-8 个）"
            className="glass-deep flex-1 rounded-xl px-3 py-2 text-[13px] text-zinc-200 outline-none placeholder:text-zinc-600"
          />
          <select
            value={draft.importance}
            onChange={(e) => setDraft({ ...draft, importance: Number(e.target.value) })}
            className="glass-deep rounded-xl px-2.5 py-2 text-[13px] text-zinc-200 outline-none [&>option]:bg-ink-900"
            title="重要度 1-5，影响常驻注入与召回排序"
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                重要度 {n}
              </option>
            ))}
          </select>
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={() => setEditing(false)}
            className="flex items-center gap-1 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-zinc-300 transition hover:text-zinc-100"
          >
            <X className="size-3.5" />
            取消
          </button>
          <button
            onClick={() => void save()}
            disabled={saving}
            className="flex items-center gap-1 rounded-xl border border-aurora-cyan/25 bg-aurora-cyan/10 px-3 py-1.5 text-xs text-aurora-cyan transition hover:bg-aurora-cyan/20 disabled:opacity-40"
          >
            {saving ? <Spinner className="size-3.5" /> : <Check className="size-3.5" />}
            保存
          </button>
        </div>
      </GlassPanel>
    )
  }

  return (
    <GlassPanel className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div
          className="min-w-0 flex-1 cursor-pointer"
          onClick={() => void expand()}
          title={detail ? undefined : '点击展开内容'}
        >
          <div className="flex items-center gap-2">
            <span className="truncate text-sm text-zinc-100">{memory.title}</span>
            <span
              className="flex shrink-0 items-center gap-0.5"
              title={`重要度 ${memory.importance ?? 3}`}
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <Star
                  key={n}
                  className={cn(
                    'size-3',
                    n <= (memory.importance ?? 3)
                      ? 'fill-amber-300/80 text-amber-300/80'
                      : 'text-zinc-700'
                  )}
                />
              ))}
            </span>
          </div>
          {memory.keywords.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {memory.keywords.map((k) => (
                <span
                  key={k}
                  className="rounded-full border border-white/[0.07] bg-white/[0.04] px-2 py-0.5 text-[11px] text-zinc-400"
                >
                  {k}
                </span>
              ))}
            </div>
          )}
          {loadingDetail && <div className="mt-2 text-xs text-zinc-500">读取中…</div>}
          {detail && (
            <p className="mt-2 whitespace-pre-wrap text-[13px] leading-6 text-zinc-300">
              {detail.content}
            </p>
          )}
          {detail && (
            <p className="mt-1.5 text-[11px] text-zinc-600">
              {memory.source === 'chat' ? '来自对话 · ' : ''}
              {memory.created_at.slice(0, 10)}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            onClick={() => void expand().then((entry) => entry && startEdit(entry))}
            className="grid size-7 place-items-center rounded-lg text-zinc-500 transition hover:bg-white/[0.06] hover:text-zinc-200"
            aria-label="编辑记忆"
          >
            <Pencil className="size-3.5" />
          </button>
          <button
            onClick={() => void remove()}
            className="grid size-7 place-items-center rounded-lg text-zinc-500 transition hover:bg-rose-500/15 hover:text-rose-300"
            aria-label="删除记忆"
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>
      </div>
    </GlassPanel>
  )
}
