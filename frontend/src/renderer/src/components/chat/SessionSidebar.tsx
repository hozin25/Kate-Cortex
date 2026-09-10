import { useEffect, useRef, useState } from 'react'
import { motion } from 'motion/react'
import { Check, MessageSquarePlus, Pencil, Trash2 } from 'lucide-react'
import { useChatStore, pickStartProvider } from '@renderer/stores/chat'
import { useSettingsStore } from '@renderer/stores/settings'
import { useUiStore } from '@renderer/stores/ui'
import { toast } from '@renderer/stores/toast'
import { cn, formatTime } from '@renderer/lib/utils'
import type { ChatSession } from '@renderer/types'

export function SessionSidebar(): React.JSX.Element {
  const sessions = useChatStore((s) => s.sessions)
  const currentId = useChatStore((s) => s.currentId)
  const createSession = useChatStore((s) => s.createSession)
  const selectSession = useChatStore((s) => s.selectSession)
  const loadSessions = useChatStore((s) => s.loadSessions)
  const settings = useSettingsStore((s) => s.settings)
  const setSessionsOpen = useUiStore((s) => s.setSessionsOpen)

  useEffect(() => {
    void loadSessions().catch((err) =>
      toast.error(err instanceof Error ? err.message : '会话加载失败')
    )
  }, [loadSessions])

  const handleCreate = async (): Promise<void> => {
    try {
      await createSession(pickStartProvider(settings))
      setSessionsOpen(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '创建会话失败')
    }
  }

  const handleSelect = (id: string): void => {
    void selectSession(id)
    setSessionsOpen(false)
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="px-3 pb-2">
        <button
          onClick={() => void handleCreate()}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-aurora-indigo/30 bg-gradient-to-r from-aurora-indigo/20 to-aurora-violet/15 px-3 py-2 text-[13px] font-medium text-zinc-100 transition hover:brightness-125"
        >
          <MessageSquarePlus className="size-4" />
          新会话
          <kbd className="hidden rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-zinc-400 md:inline">
            Ctrl+N
          </kbd>
        </button>
      </div>
      <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
        {sessions.map((s) => (
          <SessionRow
            key={s.id}
            session={s}
            active={s.id === currentId}
            onSelect={() => handleSelect(s.id)}
          />
        ))}
        {sessions.length === 0 && (
          <p className="px-3 py-6 text-center text-xs leading-5 text-zinc-600">
            还没有对话
            <br />
            点击上方按钮开始
          </p>
        )}
      </div>
    </div>
  )
}

interface SessionRowProps {
  session: ChatSession
  active: boolean
  onSelect: () => void
}

function SessionRow({ session, active, onSelect }: SessionRowProps): React.JSX.Element {
  const renameSession = useChatStore((s) => s.renameSession)
  const removeSession = useChatStore((s) => s.removeSession)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(session.title ?? '')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) inputRef.current?.select()
  }, [editing])

  const commitRename = async (): Promise<void> => {
    setEditing(false)
    const title = draft.trim()
    if (!title || title === session.title) return
    try {
      await renameSession(session.id, title)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '重命名失败')
    }
  }

  const handleDelete = async (): Promise<void> => {
    try {
      await removeSession(session.id)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  return (
    <div
      onClick={onSelect}
      className={cn(
        'group relative cursor-pointer rounded-xl border px-3 py-2 transition',
        active
          ? 'border-aurora-indigo/30 bg-aurora-indigo/12'
          : 'border-transparent hover:border-white/[0.08] hover:bg-white/[0.04]'
      )}
    >
      {editing ? (
        <div className="flex items-center gap-1.5">
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void commitRename()
              if (e.key === 'Escape') setEditing(false)
            }}
            onBlur={() => void commitRename()}
            className="w-full rounded-md border border-aurora-cyan/30 bg-ink-950/60 px-2 py-1 text-[13px] text-zinc-100 outline-none"
            onClick={(e) => e.stopPropagation()}
            autoFocus
          />
          <button
            onClick={(e) => {
              e.stopPropagation()
              void commitRename()
            }}
            className="rounded-md p-1 text-emerald-300 hover:bg-white/10"
          >
            <Check className="size-3.5" />
          </button>
        </div>
      ) : (
        <>
          <div className={cn('truncate text-[13px]', active ? 'text-zinc-100' : 'text-zinc-300')}>
            {session.title ?? '新会话'}
          </div>
          <div className="mt-0.5 flex items-center justify-between gap-2">
            <span className="truncate text-[11px] text-zinc-600">
              {session.preview || formatTime(session.updated_at)}
            </span>
            <span className="shrink-0 rounded bg-white/[0.06] px-1 py-px text-[9px] uppercase tracking-wider text-zinc-500">
              {session.provider}
            </span>
          </div>
          <div className="absolute right-2 top-1.5 hidden gap-0.5 group-hover:flex">
            <motion.button
              whileHover={{ scale: 1.08 }}
              onClick={(e) => {
                e.stopPropagation()
                setDraft(session.title ?? '')
                setEditing(true)
              }}
              className="rounded-md bg-ink-950/70 p-1 text-zinc-400 hover:text-zinc-100"
              aria-label="重命名"
            >
              <Pencil className="size-3" />
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.08 }}
              onClick={(e) => {
                e.stopPropagation()
                void handleDelete()
              }}
              className="rounded-md bg-ink-950/70 p-1 text-zinc-400 hover:text-rose-300"
              aria-label="删除"
            >
              <Trash2 className="size-3" />
            </motion.button>
          </div>
        </>
      )}
    </div>
  )
}
