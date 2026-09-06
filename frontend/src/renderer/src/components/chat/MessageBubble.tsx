import { useState } from 'react'
import { motion } from 'motion/react'
import { Link } from 'react-router-dom'
import { BookOpen, Check, Copy, Pencil, RefreshCw, Trash2, X } from 'lucide-react'
import { MarkdownView } from '@renderer/components/common/MarkdownView'
import { toast } from '@renderer/stores/toast'
import { formatTime } from '@renderer/lib/utils'
import { cn } from '@renderer/lib/utils'
import type { ChatMessage } from '@renderer/types'

interface MessageBubbleProps {
  message: ChatMessage
  isLast?: boolean
  streaming?: boolean
  onRegenerate?: () => void
  onEdit?: (content: string) => void
  onDelete?: () => void
}

const IMAGE_REF_RE = /!\[[^\]]*\]\(attachments\/[^)]+\)/g

function stripImageRefs(content: string): string {
  return content.replace(IMAGE_REF_RE, '').trim()
}

export function MessageBubble({
  message,
  isLast = false,
  streaming = false,
  onRegenerate,
  onEdit,
  onDelete
}: MessageBubbleProps): React.JSX.Element {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  if (message.role === 'user' && editing) {
    const resend = (): void => {
      const content = draft.trim()
      if (!content) return
      setEditing(false)
      onEdit?.(content)
    }
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex w-full justify-end"
      >
        <div className="flex w-[80%] flex-col gap-2 rounded-2xl rounded-br-md border border-aurora-indigo/25 bg-aurora-indigo/15 p-3">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={Math.min(6, Math.max(2, draft.split('\n').length))}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault()
                resend()
              }
              if (e.key === 'Escape') setEditing(false)
            }}
            className="glass-deep w-full resize-none rounded-xl px-3 py-2 text-sm leading-6 text-zinc-100 outline-none"
          />
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setEditing(false)}
              className="flex items-center gap-1 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-zinc-300 transition hover:text-zinc-100"
            >
              <X className="size-3.5" />
              取消
            </button>
            <button
              onClick={resend}
              className="flex items-center gap-1 rounded-xl border border-aurora-cyan/25 bg-aurora-cyan/10 px-3 py-1.5 text-xs text-aurora-cyan transition hover:bg-aurora-cyan/20"
            >
              <Check className="size-3.5" />
              重发
            </button>
          </div>
        </div>
      </motion.div>
    )
  }

  const copy = (): void => {
    void navigator.clipboard
      .writeText(message.content)
      .then(() => toast.success('已复制'))
      .catch(() => toast.error('复制失败'))
  }

  const edit = (): void => {
    setDraft(stripImageRefs(message.content))
    setEditing(true)
  }

  if (message.role === 'user') {
    // 含图片引用（附件路径或乐观渲染的 data URL）时走 markdown 渲染，纯文本保持原样
    const hasImages = /!\[[^\]]*\]\((attachments\/|data:)/.test(message.content)
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: [0.21, 1, 0.35, 1] }}
        className="group flex justify-end"
      >
        <div className="flex max-w-[80%] items-start gap-1.5">
          <div className="flex shrink-0 items-center gap-0.5 pt-1 opacity-0 transition group-hover:opacity-100">
            <ActionIcon label="复制" onClick={copy} icon={<Copy className="size-3.5" />} />
            <ActionIcon label="编辑" onClick={edit} icon={<Pencil className="size-3.5" />} />
            <ActionIcon
              label="删除"
              onClick={() => onDelete?.()}
              danger
              icon={<Trash2 className="size-3.5" />}
            />
          </div>
          <div className="max-w-full rounded-2xl rounded-br-md border border-aurora-indigo/25 bg-aurora-indigo/15 px-4 py-2.5 text-sm leading-7 text-zinc-100">
            {hasImages ? (
              <MarkdownView content={message.content} />
            ) : (
              <p className="whitespace-pre-wrap">{message.content}</p>
            )}
          </div>
        </div>
      </motion.div>
    )
  }

  const refs = message.knowledge_refs ?? []
  const canRegenerate = isLast && !streaming && onRegenerate !== undefined
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.21, 1, 0.35, 1] }}
      className="group flex flex-col gap-2"
    >
      <div className="flex items-center gap-2 text-[11px] text-zinc-500">
        <span className="font-display text-xs tracking-wide text-aurora-cyan/80">Kate</span>
        <span>{formatTime(message.created_at)}</span>
        {refs.length > 0 && (
          <span className="flex items-center gap-1 text-zinc-600">
            <BookOpen className="size-3" />
            参考 {refs.length} 条
            {refs.map((r) => (
              <Link
                key={r}
                to={`/entries/${r}`}
                className="underline decoration-dotted hover:text-aurora-cyan"
              >
                ↗
              </Link>
            ))}
          </span>
        )}
      </div>
      <div className="flex max-w-[92%] items-start gap-1.5">
        <div className="max-w-full rounded-2xl rounded-bl-md border border-white/[0.07] bg-white/[0.035] px-4 py-2.5">
          <MarkdownView content={message.content || '（无文本内容）'} />
        </div>
        <div className="flex shrink-0 items-center gap-0.5 pt-1 opacity-0 transition group-hover:opacity-100">
          <ActionIcon label="复制" onClick={copy} icon={<Copy className="size-3.5" />} />
          {canRegenerate && (
            <ActionIcon
              label="重新生成"
              onClick={() => onRegenerate?.()}
              icon={<RefreshCw className="size-3.5" />}
            />
          )}
          <ActionIcon
            label="删除"
            onClick={() => onDelete?.()}
            danger
            icon={<Trash2 className="size-3.5" />}
          />
        </div>
      </div>
    </motion.div>
  )
}

interface ActionIconProps {
  label: string
  onClick: () => void
  icon: React.JSX.Element
  danger?: boolean
}

function ActionIcon({ label, onClick, icon, danger }: ActionIconProps): React.JSX.Element {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className={cn(
        'grid size-6 place-items-center rounded-lg text-zinc-600 transition hover:bg-white/[0.06]',
        danger ? 'hover:text-rose-300' : 'hover:text-zinc-200'
      )}
    >
      {icon}
    </button>
  )
}

export function StreamingBubble({ text }: { text: string }): React.JSX.Element {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 text-[11px] text-zinc-500">
        <span className="font-display text-xs tracking-wide text-aurora-cyan/80">Kate</span>
        <span className="animate-pulse">正在思考…</span>
      </div>
      <div className="max-w-[92%] rounded-2xl rounded-bl-md border border-white/[0.07] bg-white/[0.035] px-4 py-2.5">
        <div className="flex items-start gap-1">
          <MarkdownView content={text} />
          <span className="mt-1 inline-block h-4 w-[7px] shrink-0 animate-cursor-blink rounded-[2px] bg-aurora-cyan/90" />
        </div>
      </div>
    </div>
  )
}
