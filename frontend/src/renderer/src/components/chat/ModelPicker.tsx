import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, Cpu } from 'lucide-react'
import { cn } from '@renderer/lib/utils'
import type { ChatSession, ProviderCatalog, ProviderName } from '@renderer/types'

const PROVIDER_LABELS: Record<ProviderName, string> = {
  glm: 'GLM 智谱',
  'glm-coding': 'GLM 编程套餐',
  siliconflow: '硅基流动',
  modelscope: '魔搭 ModelScope',
  deepseek: 'DeepSeek'
}

function freeNote(provider: ProviderName): string {
  return provider === 'modelscope' ? '每日免费' : '免费'
}

/** 当前会话模型的短显示名：目录里有就用展示名，否则取 id 末段 */
function shortModel(catalog: ProviderCatalog[] | null, session: ChatSession): string {
  const group = catalog?.find((p) => p.name === session.provider)
  const hit = group?.models.find((m) => m.model === session.model)
  return hit?.label ?? session.model.split('/').pop() ?? session.model
}

interface ModelPickerProps {
  session: ChatSession
  /** ChatPage 预取的 /api/models 目录（null = 加载中） */
  catalog: ProviderCatalog[] | null
  disabled?: boolean
  onSwitch: (provider: ProviderName, model: string) => void
}

export function ModelPicker({
  session,
  catalog,
  disabled = false,
  onSwitch
}: ModelPickerProps): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  // 点击组件外部关闭弹层
  useEffect(() => {
    if (!open) return
    const onDocClick = (e: MouseEvent): void => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [open])

  const current = shortModel(catalog, session)

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={() => setOpen(!open)}
        disabled={disabled}
        className={cn(
          'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition',
          open
            ? 'border-aurora-indigo/40 bg-aurora-indigo/15 text-zinc-100'
            : 'border-white/10 bg-white/[0.04] text-zinc-400 hover:text-zinc-200',
          disabled && 'cursor-not-allowed opacity-50'
        )}
        title="切换当前对话的模型"
      >
        <Cpu className="size-3" />
        <span className="max-w-52 truncate">
          {PROVIDER_LABELS[session.provider as ProviderName] ?? session.provider}
          <span className="mx-1 text-zinc-600">·</span>
          {current}
        </span>
        <ChevronDown className={cn('size-3 transition', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="glass-deep absolute right-0 top-full z-20 mt-2 max-h-80 w-72 overflow-y-auto rounded-xl border border-white/10 p-1.5 shadow-xl shadow-black/40">
          {catalog === null && (
            <p className="px-3 py-4 text-center text-xs text-zinc-500">加载中…</p>
          )}
          {catalog?.length === 0 && (
            <p className="px-3 py-4 text-center text-xs text-zinc-500">模型目录加载失败</p>
          )}
          {catalog?.map((group) => {
            const usable = group.has_key
            return (
              <div key={group.name} className="mb-1 last:mb-0">
                <div className="flex items-center justify-between px-2.5 pb-1 pt-2">
                  <span
                    className={cn(
                      'text-[11px] font-medium',
                      usable ? 'text-zinc-300' : 'text-zinc-600'
                    )}
                  >
                    {PROVIDER_LABELS[group.name] ?? group.name}
                  </span>
                  {!usable && <span className="text-[10px] text-zinc-600">未配置 Key</span>}
                </div>
                {group.models.map((m) => {
                  const active =
                    session.provider === group.name && session.model === m.model
                  return (
                    <button
                      key={m.model}
                      disabled={!usable || active}
                      onClick={() => {
                        setOpen(false)
                        onSwitch(group.name, m.model)
                      }}
                      className={cn(
                        'flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition',
                        active
                          ? 'bg-aurora-indigo/15 text-zinc-100'
                          : usable
                            ? 'text-zinc-300 hover:bg-white/[0.06] hover:text-zinc-100'
                            : 'cursor-not-allowed text-zinc-600'
                      )}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate">{m.label}</span>
                        <span className="block truncate font-mono text-[10px] text-zinc-500">
                          {m.model}
                        </span>
                      </span>
                      {m.free && (
                        <span
                          className={cn(
                            'shrink-0 rounded px-1 py-px text-[9px]',
                            usable
                              ? 'bg-emerald-400/15 text-emerald-300'
                              : 'bg-white/[0.04] text-zinc-600'
                          )}
                        >
                          {freeNote(group.name)}
                        </span>
                      )}
                      {m.vision && (
                        <span
                          className={cn(
                            'shrink-0 rounded px-1 py-px text-[9px]',
                            usable
                              ? 'bg-violet-400/15 text-violet-300'
                              : 'bg-white/[0.04] text-zinc-600'
                          )}
                          title="支持图片输入"
                        >
                          视觉
                        </span>
                      )}
                      {active && <Check className="size-3.5 shrink-0 text-aurora-cyan" />}
                    </button>
                  )
                })}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
