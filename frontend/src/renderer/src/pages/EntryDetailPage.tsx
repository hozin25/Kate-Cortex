import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { motion } from 'motion/react'
import { ArrowLeft, ArrowUpLeft, Link2, MessagesSquare, Pencil, Trash2 } from 'lucide-react'
import { api } from '@renderer/api/client'
import { MarkdownView } from '@renderer/components/common/MarkdownView'
import { Spinner, TypeBadge } from '@renderer/components/common/Badges'
import { EmptyState } from '@renderer/components/common/EmptyState'
import { toast } from '@renderer/stores/toast'
import { formatTime } from '@renderer/lib/utils'
import type { Entry, EntrySummary } from '@renderer/types'

interface LoadState {
  loadedId: string
  entry: Entry | null
  backlinks: EntrySummary[]
  missing: boolean
}

export function EntryDetailPage(): React.JSX.Element {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [state, setState] = useState<LoadState | null>(null)

  useEffect(() => {
    if (!id) return
    let alive = true
    api
      .get<Entry>(`/entries/${id}`)
      .then((entry) => {
        if (!alive) return
        setState({ loadedId: id, entry, backlinks: [], missing: false })
        return api
          .get<EntrySummary[]>(`/entries/${entry.id}/links`)
          .then((backlinks) => {
            if (alive) setState({ loadedId: id, entry, backlinks, missing: false })
          })
          .catch(() => undefined)
      })
      .catch(() => {
        if (alive) setState({ loadedId: id, entry: null, backlinks: [], missing: true })
      })
    return () => {
      alive = false
    }
  }, [id])

  const loaded = state !== null && state.loadedId === id ? state : null
  const entry = loaded?.entry ?? null
  const backlinks = loaded?.backlinks ?? []
  const missing = loaded?.missing ?? false

  if (missing) {
    return (
      <EmptyState
        icon={<Link2 className="size-6" />}
        title="条目不存在"
        hint="它可能已被删除，或链接已失效"
        action={
          <Link to="/library" className="text-xs text-aurora-cyan hover:underline">
            返回知识库
          </Link>
        }
      />
    )
  }

  if (!entry) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="size-6 text-zinc-500" />
      </div>
    )
  }

  const handleDelete = async (): Promise<void> => {
    try {
      await api.delete(`/entries/${entry.id}`)
      toast.info(`已删除《${entry.title}》（可在 .trash 中恢复）`)
      navigate('/library')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto px-8 py-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.21, 1, 0.35, 1] }}
        className="mx-auto max-w-3xl"
      >
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <Link to="/library" className="flex items-center gap-1 transition hover:text-zinc-300">
            <ArrowLeft className="size-3.5" />
            知识库
          </Link>
          <span className="text-zinc-700">/</span>
          <span className="truncate text-zinc-600">{entry.slug}</span>
        </div>

        <div className="mt-3 flex items-start justify-between gap-4">
          <h1 className="font-display text-xl leading-8 text-zinc-50">{entry.title}</h1>
          <div className="flex shrink-0 gap-1.5">
            <Link
              to={`/entries/${entry.id}/edit`}
              className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-1.5 text-xs text-zinc-300 transition hover:text-zinc-100"
            >
              <Pencil className="size-3.5" />
              编辑
            </Link>
            <button
              onClick={() => void handleDelete()}
              className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-1.5 text-xs text-zinc-400 transition hover:border-rose-400/30 hover:text-rose-300"
            >
              <Trash2 className="size-3.5" />
              删除
            </button>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <TypeBadge type={entry.type} />
          {entry.source === 'chat' && entry.conversation_id && (
            <button
              onClick={() => navigate(`/?session=${entry.conversation_id}`)}
              className="flex items-center gap-1 rounded-full border border-aurora-violet/25 bg-aurora-violet/10 px-2 py-0.5 text-[11px] text-aurora-violet transition hover:bg-aurora-violet/20"
            >
              <MessagesSquare className="size-3" />
              来自对话 · 查看
            </button>
          )}
          {entry.tags.map((t) => (
            <Link
              key={t}
              to={`/library?tag=${encodeURIComponent(t)}`}
              className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[11px] text-zinc-400 transition hover:text-zinc-200"
            >
              #{t}
            </Link>
          ))}
          <span className="ml-auto text-[11px] text-zinc-600">
            创建 {formatTime(entry.created_at)} · 更新 {formatTime(entry.updated_at)}
          </span>
        </div>

        <div className="glass mt-5 rounded-2xl p-6">
          <MarkdownView content={entry.content || '（无正文）'} />
        </div>

        <div className="mt-5">
          <div className="flex items-center gap-1.5 text-xs text-zinc-500">
            <ArrowUpLeft className="size-3.5" />
            反向链接（{backlinks.length}）
          </div>
          {backlinks.length > 0 ? (
            <div className="mt-2 flex flex-col gap-1.5">
              {backlinks.map((b) => (
                <Link
                  key={b.id}
                  to={`/entries/${b.id}`}
                  className="glass-deep flex items-center gap-2 rounded-xl px-3 py-2 text-[13px] text-zinc-300 transition hover:text-zinc-100"
                >
                  <TypeBadge type={b.type} />
                  <span className="truncate">{b.title}</span>
                </Link>
              ))}
            </div>
          ) : (
            <p className="mt-1 text-xs text-zinc-600">
              暂无其他条目通过 [[{entry.slug}]] 链接到这里
            </p>
          )}
        </div>
      </motion.div>
    </div>
  )
}
