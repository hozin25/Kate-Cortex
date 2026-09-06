import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, RotateCcw, Trash2 } from 'lucide-react'
import { GlassPanel } from '@renderer/components/common/Glass'
import { Spinner } from '@renderer/components/common/Badges'
import { EmptyState } from '@renderer/components/common/EmptyState'
import { api } from '@renderer/api/client'
import { toast } from '@renderer/stores/toast'
import type { TrashedEntry } from '@renderer/types'

export function TrashPage(): React.JSX.Element {
  const [items, setItems] = useState<TrashedEntry[] | null>(null)

  const load = useCallback((): Promise<void> => {
    return api
      .get<TrashedEntry[]>('/trash')
      .then(setItems)
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : '回收站加载失败')
        setItems([])
      })
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const restore = async (id: string, title: string): Promise<void> => {
    try {
      await api.post(`/entries/${id}/restore`)
      toast.success(`已恢复《${title}》`)
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '恢复失败')
    }
  }

  const purge = async (id: string, title: string): Promise<void> => {
    if (!window.confirm(`彻底删除《${title}》？此操作不可恢复。`)) return
    try {
      await api.delete(`/trash/${id}`)
      toast.success('已彻底删除')
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  return (
    <div className="h-full overflow-y-auto px-8 py-6">
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <div className="flex items-center justify-between">
          <h1 className="font-display text-lg text-zinc-100">
            回收站{' '}
            {items !== null && (
              <span className="ml-1 text-sm text-zinc-500">{items.length} 条</span>
            )}
          </h1>
          <Link
            to="/library"
            className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[13px] text-zinc-300 transition hover:text-zinc-100"
          >
            <ArrowLeft className="size-3.5" />
            返回知识库
          </Link>
        </div>
        <p className="text-xs leading-5 text-zinc-500">
          删除的条目在此保留 30 天，可恢复或彻底删除；超期文件会在应用启动时自动清理。
        </p>

        {items === null ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-6 text-zinc-500" />
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<Trash2 className="size-7" />}
            title="回收站是空的"
            hint="删除的知识条目会先进入这里，30 天内可随时恢复。"
          />
        ) : (
          <div className="flex flex-col gap-2.5">
            {items.map((t) => (
              <GlassPanel key={t.id} className="flex items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <div className="truncate text-sm text-zinc-100">{t.title}</div>
                  <div className="mt-0.5 font-mono text-[11px] text-zinc-600">
                    {t.file_path} · 删除于 {t.deleted_at.slice(0, 16).replace('T', ' ')}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    onClick={() => void restore(t.id, t.title)}
                    className="flex items-center gap-1 rounded-xl border border-aurora-cyan/25 bg-aurora-cyan/10 px-3 py-1.5 text-xs text-aurora-cyan transition hover:bg-aurora-cyan/20"
                  >
                    <RotateCcw className="size-3.5" />
                    恢复
                  </button>
                  <button
                    onClick={() => void purge(t.id, t.title)}
                    className="flex items-center gap-1 rounded-xl border border-rose-400/25 bg-rose-500/10 px-3 py-1.5 text-xs text-rose-300 transition hover:bg-rose-500/20"
                  >
                    <Trash2 className="size-3.5" />
                    彻底删除
                  </button>
                </div>
              </GlassPanel>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
