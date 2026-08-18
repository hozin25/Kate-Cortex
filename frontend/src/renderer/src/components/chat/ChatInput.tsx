import { useRef } from 'react'
import { Send, Square } from 'lucide-react'
import { cn } from '@renderer/lib/utils'

interface ChatInputProps {
  streaming: boolean
  onSend: (content: string) => void
  onStop: () => void
}

export function ChatInput({ streaming, onSend, onStop }: ChatInputProps): React.JSX.Element {
  const ref = useRef<HTMLTextAreaElement>(null)

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  const submit = (): void => {
    const el = ref.current
    if (!el) return
    const content = el.value.trim()
    if (!content || streaming) return
    onSend(content)
    el.value = ''
    el.style.height = 'auto'
  }

  const autoSize = (el: HTMLTextAreaElement): void => {
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  return (
    <div className="glass mx-auto flex w-full max-w-3xl items-end gap-2 rounded-2xl p-2">
      <textarea
        ref={ref}
        rows={1}
        placeholder="和 Kate 聊聊…（Enter 发送，Shift+Enter 换行）"
        className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-600"
        onKeyDown={handleKeyDown}
        onInput={(e) => autoSize(e.currentTarget)}
      />
      {streaming ? (
        <button
          onClick={onStop}
          className="grid size-9 shrink-0 place-items-center rounded-xl border border-rose-400/30 bg-rose-500/15 text-rose-300 transition hover:bg-rose-500/25"
          aria-label="停止生成"
        >
          <Square className="size-4" />
        </button>
      ) : (
        <button
          onClick={submit}
          className="grid size-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-aurora-indigo to-aurora-violet text-white shadow-lg shadow-aurora-indigo/25 transition hover:brightness-110 disabled:opacity-40"
          aria-label="发送"
        >
          <Send className="size-4" />
        </button>
      )}
    </div>
  )
}

interface RagToggleProps {
  enabled: boolean
  onChange: (enabled: boolean) => void
  className?: string
}

export function RagToggle({ enabled, onChange, className }: RagToggleProps): React.JSX.Element {
  return (
    <button
      onClick={() => onChange(!enabled)}
      className={cn(
        'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition',
        enabled
          ? 'border-aurora-cyan/35 bg-aurora-cyan/12 text-aurora-cyan'
          : 'border-white/10 bg-white/[0.04] text-zinc-500 hover:text-zinc-300',
        className
      )}
      title="开启后 Kate 会检索你的知识库作为回答参考"
    >
      <span
        className={cn(
          'size-1.5 rounded-full',
          enabled ? 'bg-aurora-cyan shadow-[0_0_6px] shadow-aurora-cyan' : 'bg-zinc-600'
        )}
      />
      知识库引用
    </button>
  )
}
