import { useMemo, useRef, useState } from 'react'
import { Bot, ImagePlus, Send, Square, X } from 'lucide-react'
import { cn } from '@renderer/lib/utils'
import { compressImage } from '@renderer/lib/imageCompress'
import { toast } from '@renderer/stores/toast'
import type { Agent } from '@renderer/types'

const MAX_IMAGES = 4
const MAX_IMAGE_BYTES = 5 * 1024 * 1024
const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
const MAX_MENU_ITEMS = 6

interface ChatInputProps {
  streaming: boolean
  onSend: (content: string, images?: string[]) => void
  onStop: () => void
  /** 当前模型能否接收图片；null/undefined = 未知（不拦，交后端 400 兜底） */
  visionSupported?: boolean | null
  /** 可引用的自定义 agent（仅 enabled）；空数组时输入 / 不弹菜单 */
  agents?: Agent[]
}

const VISION_HINT = '当前模型不支持图片，请先在右上角切换到带「视觉」标注的模型'

interface AgentMenuState {
  query: string
  active: number
}

/** 光标之前、从输入框开头一路延续的 `/token`；不在开头或中间有空白则 null
 *  （锚定输入起点，URL 里的 / 不触发——ZCode slash 菜单同款规则） */
function slashTokenBeforeCaret(el: HTMLTextAreaElement): string | null {
  const pos = el.selectionStart ?? el.value.length
  const match = /^\/(\S*)$/.exec(el.value.slice(0, pos))
  return match ? match[1] : null
}

export function ChatInput({
  streaming,
  onSend,
  onStop,
  visionSupported = null,
  agents = []
}: ChatInputProps): React.JSX.Element {
  const ref = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [images, setImages] = useState<string[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [menu, setMenu] = useState<AgentMenuState | null>(null)
  const noVision = visionSupported === false

  const matches = useMemo(() => {
    if (!menu) return []
    const q = menu.query.toLowerCase()
    return agents.filter(
      (a) => a.name.toLowerCase().includes(q) || a.description.toLowerCase().includes(q)
    )
  }, [menu, agents])
  const activeIdx = menu && matches.length > 0 ? Math.min(menu.active, matches.length - 1) : 0

  const syncMenu = (): void => {
    const el = ref.current
    if (!el) return
    const token = slashTokenBeforeCaret(el)
    if (token === null || agents.length === 0) {
      setMenu(null)
    } else {
      // 同一 token（如点击挪动光标）保持高亮项不变
      setMenu((m) => (m && m.query === token ? m : { query: token, active: 0 }))
    }
  }

  const addFiles = async (files: FileList | File[] | null): Promise<void> => {
    if (!files) return
    if (noVision) {
      toast.info(VISION_HINT)
      return
    }
    const incoming = Array.from(files).filter((f) => ACCEPTED_TYPES.includes(f.type))
    if (incoming.length === 0) {
      if (Array.from(files).length > 0) toast.error('仅支持 png / jpeg / webp / gif 图片')
      return
    }
    if (incoming.some((f) => f.size > MAX_IMAGE_BYTES)) {
      toast.error(`图片超过 5MB 上限`)
      return
    }
    if (images.length + incoming.length > MAX_IMAGES) {
      toast.error(`单条消息最多 ${MAX_IMAGES} 张图片`)
      return
    }
    try {
      const urls = await Promise.all(incoming.map(compressImage))
      setImages([...images, ...urls])
    } catch {
      toast.error('图片读取失败')
    }
  }

  const autoSize = (el: HTMLTextAreaElement): void => {
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  /** 选中 agent：光标前的 `/partial` 替换为 `/名称 `，光标落在其后 */
  const chooseAgent = (agent: Agent): void => {
    const el = ref.current
    if (!el) return
    const pos = el.selectionStart ?? el.value.length
    const inserted = `/${agent.name} `
    el.value = el.value.slice(0, pos).replace(/^\/\S*$/, inserted) + el.value.slice(pos)
    el.setSelectionRange(inserted.length, inserted.length)
    setMenu(null)
    el.focus()
    autoSize(el)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    if (menu && !e.nativeEvent.isComposing) {
      if (e.key === 'ArrowDown' && matches.length > 0) {
        e.preventDefault()
        setMenu({ ...menu, active: (activeIdx + 1) % matches.length })
        return
      }
      if (e.key === 'ArrowUp' && matches.length > 0) {
        e.preventDefault()
        setMenu({ ...menu, active: (activeIdx - 1 + matches.length) % matches.length })
        return
      }
      if ((e.key === 'Enter' || e.key === 'Tab') && matches.length > 0) {
        // 菜单打开时 Enter/Tab 只做选中，不发送
        e.preventDefault()
        chooseAgent(matches[activeIdx])
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setMenu(null)
        return
      }
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>): void => {
    const files = e.clipboardData?.files
    if (files && files.length > 0) {
      e.preventDefault()
      void addFiles(files)
    }
  }

  const submit = (): void => {
    const el = ref.current
    if (!el) return
    const content = el.value.trim()
    if ((!content && images.length === 0) || streaming) return
    if (noVision && images.length > 0) {
      toast.info(VISION_HINT)
      return
    }
    onSend(content, images)
    el.value = ''
    el.style.height = 'auto'
    setImages([])
    setMenu(null)
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      {images.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {images.map((src, i) => (
            <div key={i} className="relative">
              <img
                src={src}
                alt={`待发送图片 ${i + 1}`}
                className="size-16 rounded-xl border border-white/10 object-cover"
              />
              <button
                onClick={() => setImages(images.filter((_, j) => j !== i))}
                className="absolute -right-1.5 -top-1.5 grid size-5 place-items-center rounded-full bg-zinc-800/95 text-zinc-300 shadow hover:text-white"
                aria-label="移除图片"
              >
                <X className="size-3" />
              </button>
            </div>
          ))}
        </div>
      )}
      <div
        className={cn(
          'glass relative flex w-full items-end gap-2 rounded-2xl p-2 transition',
          dragOver && 'ring-1 ring-aurora-cyan/50'
        )}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          void addFiles(e.dataTransfer?.files ?? null)
        }}
      >
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          multiple
          className="hidden"
          onChange={(e) => {
            void addFiles(e.target.files)
            e.target.value = ''
          }}
        />
        {menu && agents.length > 0 && (
          <div
            className="glass-deep absolute bottom-full left-0 right-0 z-10 mb-2 max-h-60 overflow-y-auto rounded-xl border border-white/10 shadow-xl shadow-black/25"
            role="listbox"
            aria-label="引用 agent"
          >
            {matches.length === 0 ? (
              <p className="px-3 py-2.5 text-xs text-zinc-500">没有匹配的 agent（到设置页创建）</p>
            ) : (
              matches.slice(0, MAX_MENU_ITEMS).map((agent, i) => (
                <button
                  key={agent.id}
                  role="option"
                  aria-selected={i === activeIdx}
                  onMouseDown={(e) => {
                    e.preventDefault() // 不让 textarea 失焦，避免 blur 抢先关菜单
                    chooseAgent(agent)
                  }}
                  onMouseEnter={() => setMenu({ ...menu, active: i })}
                  className={cn(
                    'flex w-full items-start gap-2.5 px-3 py-2 text-left transition',
                    i === activeIdx && 'bg-white/[0.06]'
                  )}
                >
                  <Bot className="mt-0.5 size-4 shrink-0 text-aurora-cyan" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-mono text-[13px] text-zinc-100">
                      /{agent.name}
                    </span>
                    {agent.description && (
                      <span className="block truncate text-[11px] text-zinc-400">
                        {agent.description}
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 pt-0.5 text-[10px] text-zinc-500">
                    {agent.provider && agent.model
                      ? `${agent.provider} · ${agent.model}`
                      : '跟随会话模型'}
                  </span>
                </button>
              ))
            )}
          </div>
        )}
        <button
          onClick={() => fileRef.current?.click()}
          disabled={streaming || images.length >= MAX_IMAGES || noVision}
          className="grid size-9 shrink-0 place-items-center rounded-xl text-zinc-400 transition hover:bg-white/[0.06] hover:text-zinc-200 disabled:opacity-40"
          aria-label="添加图片"
          title={noVision ? VISION_HINT : '添加图片（也可直接粘贴 / 拖入）'}
        >
          <ImagePlus className="size-4" />
        </button>
        <textarea
          ref={ref}
          rows={1}
          placeholder="和 Kate 聊聊…（/ 引用 agent · Enter 发送 · Shift+Enter 换行 · 可粘贴/拖入图片）"
          className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-600"
          onKeyDown={handleKeyDown}
          onInput={(e) => {
            autoSize(e.currentTarget)
            syncMenu()
          }}
          onClick={syncMenu}
          onBlur={() => setMenu(null)}
          onPaste={handlePaste}
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
