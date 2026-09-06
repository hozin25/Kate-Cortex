import { motion } from 'motion/react'
import { Link } from 'react-router-dom'
import { BookOpen } from 'lucide-react'
import { MarkdownView } from '@renderer/components/common/MarkdownView'
import { formatTime } from '@renderer/lib/utils'
import type { ChatMessage } from '@renderer/types'

interface MessageBubbleProps {
  message: ChatMessage
}

export function MessageBubble({ message }: MessageBubbleProps): React.JSX.Element {
  if (message.role === 'user') {
    // 含图片引用（附件路径或乐观渲染的 data URL）时走 markdown 渲染，纯文本保持原样
    const hasImages = /!\[[^\]]*\]\((attachments\/|data:)/.test(message.content)
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: [0.21, 1, 0.35, 1] }}
        className="flex justify-end"
      >
        <div className="max-w-[80%] rounded-2xl rounded-br-md border border-aurora-indigo/25 bg-aurora-indigo/15 px-4 py-2.5 text-sm leading-7 text-zinc-100">
          {hasImages ? (
            <MarkdownView content={message.content} />
          ) : (
            <p className="whitespace-pre-wrap">{message.content}</p>
          )}
        </div>
      </motion.div>
    )
  }

  const refs = message.knowledge_refs ?? []
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.21, 1, 0.35, 1] }}
      className="flex flex-col gap-2"
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
      <div className="max-w-[92%] rounded-2xl rounded-bl-md border border-white/[0.07] bg-white/[0.035] px-4 py-2.5">
        <MarkdownView content={message.content || '（无文本内容）'} />
      </div>
    </motion.div>
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
