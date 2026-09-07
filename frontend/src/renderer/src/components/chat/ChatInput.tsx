import { useRef, useState } from 'react'
import { ImagePlus, Send, Square, X } from 'lucide-react'
import { cn } from '@renderer/lib/utils'
import { toast } from '@renderer/stores/toast'

const MAX_IMAGES = 4
const MAX_IMAGE_BYTES = 5 * 1024 * 1024
const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']

interface ChatInputProps {
  streaming: boolean
  onSend: (content: string, images?: string[]) => void
  onStop: () => void
  /** 当前模型能否接收图片；null/undefined = 未知（不拦，交后端 400 兜底） */
  visionSupported?: boolean | null
}

const VISION_HINT = '当前模型不支持图片，请先在右上角切换到带「视觉」标注的模型'

export function ChatInput({
  streaming,
  onSend,
  onStop,
  visionSupported = null
}: ChatInputProps): React.JSX.Element {
  const ref = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [images, setImages] = useState<string[]>([])
  const [dragOver, setDragOver] = useState(false)
  const noVision = visionSupported === false

  const readAsDataUrl = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () => reject(reader.error)
      reader.readAsDataURL(file)
    })

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
      toast.error('图片超过 5MB 上限')
      return
    }
    if (images.length + incoming.length > MAX_IMAGES) {
      toast.error(`单条消息最多 ${MAX_IMAGES} 张图片`)
      return
    }
    try {
      const urls = await Promise.all(incoming.map(readAsDataUrl))
      setImages([...images, ...urls])
    } catch {
      toast.error('图片读取失败')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>): void => {
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
  }

  const autoSize = (el: HTMLTextAreaElement): void => {
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
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
          'glass flex w-full items-end gap-2 rounded-2xl p-2 transition',
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
          placeholder="和 Kate 聊聊…（Enter 发送，Shift+Enter 换行，可粘贴 / 拖入图片）"
          className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-600"
          onKeyDown={handleKeyDown}
          onInput={(e) => autoSize(e.currentTarget)}
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
