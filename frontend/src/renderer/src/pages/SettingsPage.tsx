import { useEffect, useState } from 'react'
import { Eye, EyeOff, KeyRound, Plug, Settings2 } from 'lucide-react'
import { GlassPanel } from '@renderer/components/common/Glass'
import { Spinner } from '@renderer/components/common/Badges'
import { useSettingsStore } from '@renderer/stores/settings'
import { toast } from '@renderer/stores/toast'
import { cn } from '@renderer/lib/utils'
import type { AppSettings, ProviderName } from '@renderer/types'

const PROVIDERS: { name: ProviderName; label: string; keyHint: string; modelHint: string }[] = [
  { name: 'deepseek', label: 'DeepSeek', keyHint: 'sk-…', modelHint: 'deepseek-chat' },
  { name: 'glm', label: 'GLM（智谱）', keyHint: '…xxx.Sxxxx', modelHint: 'glm-4-flash' }
]

export function SettingsPage(): React.JSX.Element {
  const { settings, load, update, testProvider, testStatus } = useSettingsStore()
  const [draftKeys, setDraftKeys] = useState<Record<string, string>>({})
  const [draftModel, setDraftModel] = useState('')
  const [visible, setVisible] = useState<Record<string, boolean>>({})

  useEffect(() => {
    void load()
      .then(() => {
        const loaded = useSettingsStore.getState().settings
        if (loaded) {
          setDraftKeys({ deepseek: '', glm: '' })
          setDraftModel(loaded.default_model)
        }
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : '设置加载失败'))
  }, [load])

  if (!settings) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="size-6 text-zinc-500" />
      </div>
    )
  }

  const handleSave = async (patch: Partial<AppSettings>): Promise<void> => {
    try {
      await update(patch)
      toast.success('设置已保存')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  const keyChanged = (p: ProviderName): boolean => draftKeys[p]?.trim().length > 0

  return (
    <div className="h-full overflow-y-auto px-8 py-6">
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <h1 className="font-display text-lg text-zinc-100">设置</h1>

        <GlassPanel className="p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
            <KeyRound className="size-4 text-aurora-cyan" />
            API Key
          </div>
          <p className="mt-1 text-xs leading-5 text-zinc-500">
            Key 保存在本地 SQLite，仅用于从本机直连对应服务商。填写后点击「测试」验证连通。
          </p>
          <div className="mt-4 space-y-4">
            {PROVIDERS.map((p) => {
              const stored = settings.provider_keys[p.name]
              const status = testStatus[p.name]
              return (
                <div key={p.name}>
                  <div className="flex items-center gap-2">
                    <span className="w-24 text-[13px] text-zinc-300">{p.label}</span>
                    <div className="relative flex-1">
                      <input
                        type={visible[p.name] ? 'text' : 'password'}
                        value={draftKeys[p.name]}
                        onChange={(e) => setDraftKeys({ ...draftKeys, [p.name]: e.target.value })}
                        placeholder={stored ? '已保存（输入以覆盖）' : p.keyHint}
                        className="glass-deep w-full rounded-xl px-3 py-2 pr-9 font-mono text-[13px] text-zinc-200 outline-none placeholder:font-sans placeholder:text-zinc-600"
                      />
                      <button
                        onClick={() => setVisible({ ...visible, [p.name]: !visible[p.name] })}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
                        aria-label="显示/隐藏"
                      >
                        {visible[p.name] ? (
                          <EyeOff className="size-4" />
                        ) : (
                          <Eye className="size-4" />
                        )}
                      </button>
                    </div>
                    <button
                      onClick={() =>
                        void handleSave({
                          provider_keys: {
                            ...settings.provider_keys,
                            [p.name]: draftKeys[p.name].trim()
                          }
                        })
                      }
                      disabled={!keyChanged(p.name)}
                      className="shrink-0 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-300 transition hover:text-zinc-100 disabled:opacity-40"
                    >
                      保存
                    </button>
                    <button
                      onClick={() => void testProvider(p.name)}
                      disabled={!stored && !keyChanged(p.name)}
                      className="flex shrink-0 items-center gap-1 rounded-xl border border-aurora-cyan/25 bg-aurora-cyan/10 px-3 py-2 text-xs text-aurora-cyan transition hover:bg-aurora-cyan/20 disabled:opacity-40"
                    >
                      <Plug className="size-3.5" />
                      测试
                    </button>
                  </div>
                  {status && (
                    <p
                      className={cn(
                        'mt-1.5 pl-26 text-xs',
                        status.ok ? 'text-emerald-300/90' : 'text-rose-300/90'
                      )}
                    >
                      {status.ok ? '✓' : '✕'} {status.message}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        </GlassPanel>

        <GlassPanel className="p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
            <Settings2 className="size-4 text-aurora-indigo" />
            默认模型
          </div>
          <div className="mt-3 flex items-center gap-2">
            <select
              value={settings.default_provider}
              onChange={(e) => {
                const hint = PROVIDERS.find((p) => p.name === e.target.value)?.modelHint
                setDraftModel(hint ?? '')
                void handleSave({
                  default_provider: e.target.value as ProviderName,
                  default_model: hint
                })
              }}
              className="glass-deep rounded-xl px-3 py-2 text-[13px] text-zinc-200 outline-none [&>option]:bg-ink-900"
            >
              {PROVIDERS.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.label}
                </option>
              ))}
            </select>
            <input
              value={draftModel}
              onChange={(e) => setDraftModel(e.target.value)}
              placeholder={PROVIDERS.find((p) => p.name === settings.default_provider)?.modelHint}
              className="glass-deep flex-1 rounded-xl px-3 py-2 font-mono text-[13px] text-zinc-200 outline-none placeholder:text-zinc-600"
            />
            <button
              onClick={() => void handleSave({ default_model: draftModel.trim() })}
              disabled={draftModel.trim() === settings.default_model || !draftModel.trim()}
              className="shrink-0 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-300 transition hover:text-zinc-100 disabled:opacity-40"
            >
              保存
            </button>
          </div>
        </GlassPanel>

        <GlassPanel className="flex items-center justify-between p-5">
          <div>
            <div className="text-sm font-medium text-zinc-200">知识库引用（RAG）默认开关</div>
            <p className="mt-1 text-xs leading-5 text-zinc-500">
              开启后，新对话提问时 Kate 会自动检索知识库相关条目作为回答参考。对话中可单独切换。
            </p>
          </div>
          <ToggleSwitch
            checked={settings.rag_default}
            onChange={(v) => void handleSave({ rag_default: v })}
          />
        </GlassPanel>

        <GlassPanel className="p-5">
          <div className="text-sm font-medium text-zinc-200">Vault 路径</div>
          <p className="mt-1 break-all font-mono text-xs leading-5 text-zinc-500">
            {settings.vault_path ?? '（使用默认路径）'}
          </p>
          <p className="mt-2 text-[11px] leading-4 text-zinc-600">
            所有笔记以 Markdown
            文件存于此目录，可直接用任意编辑器打开。当前版本暂不支持在界面内修改。
          </p>
        </GlassPanel>
      </div>
    </div>
  )
}

interface ToggleSwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
}

function ToggleSwitch({ checked, onChange }: ToggleSwitchProps): React.JSX.Element {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={cn(
        'relative h-6 w-11 shrink-0 rounded-full border transition',
        checked ? 'border-aurora-cyan/40 bg-aurora-cyan/25' : 'border-white/10 bg-white/[0.06]'
      )}
      role="switch"
      aria-checked={checked}
    >
      <span
        className={cn(
          'absolute top-0.5 size-4.5 rounded-full transition-all',
          checked
            ? 'left-[22px] bg-aurora-cyan shadow-[0_0_8px] shadow-aurora-cyan'
            : 'left-0.5 bg-zinc-400'
        )}
      />
    </button>
  )
}
