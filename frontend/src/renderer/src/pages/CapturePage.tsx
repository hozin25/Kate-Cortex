import { useEffect, useRef, useState } from 'react'
import { Zap } from 'lucide-react'
import { api } from '@renderer/api/client'
import { toast } from '@renderer/stores/toast'

interface CaptureResult {
  entry_id: string
  title: string
  enriched: boolean
  hint?: string | null
}

/**
 * 全局速记窗（CAPTURE_PLAN.md §3）：无边框小窗里的三秒闪记。
 * Ctrl/⌘+Enter 保存（落库即加工），Esc 关闭（主进程拦截为隐藏）。
 */
export function CapturePage(): React.JSX.Element {
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const save = async (): Promise<void> => {
    const content = text.trim()
    if (!content || saving) return
    setSaving(true)
    try {
      const result = await api.post<CaptureResult>('/capture', { text: content })
      toast.success(
        result.enriched ? `已记下：${result.title}` : `已记下：${result.title}（元数据稍后补）`
      )
      setText('')
      window.close()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
      setSaving(false)
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-white/[0.08] bg-ink-950/90">
      <div className="flex items-center gap-2 border-b border-white/[0.06] px-3 py-2 [-webkit-app-region:drag]">
        <Zap className="size-3.5 text-aurora-cyan" />
        <span className="font-display text-[11px] uppercase tracking-[0.25em] text-zinc-400">
          Kate 速记
        </span>
        <span className="ml-auto text-[10px] text-zinc-600">Ctrl+Enter 保存 · Esc 关闭</span>
      </div>
      <textarea
        ref={textareaRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            window.close()
          } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            void save()
          }
        }}
        placeholder="想到什么记什么…（首行将作为标题，保存后自动补关键词与合集）"
        className="min-h-0 flex-1 resize-none bg-transparent px-4 py-3 text-[13px] leading-6 text-zinc-100 outline-none placeholder:text-zinc-600"
      />
      <div className="flex items-center justify-between border-t border-white/[0.06] px-3 py-2">
        <span className="text-[10px] text-zinc-600">
          {text.trim().length > 0 ? `${text.trim().length} 字` : ''}
        </span>
        <button
          onClick={() => void save()}
          disabled={!text.trim() || saving}
          className="flex items-center gap-1 rounded-xl border border-aurora-cyan/30 bg-aurora-cyan/15 px-3.5 py-1.5 text-xs text-zinc-100 transition hover:brightness-125 disabled:opacity-40"
        >
          <Zap className="size-3.5" />
          {saving ? '记下中…' : '记下'}
        </button>
      </div>
    </div>
  )
}
