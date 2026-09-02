import { useEffect, useState } from 'react'
import { Eye, EyeOff, FileDown, Globe, KeyRound, Layers, Plug, Settings2 } from 'lucide-react'
import { GlassPanel } from '@renderer/components/common/Glass'
import { Spinner } from '@renderer/components/common/Badges'
import { useSettingsStore } from '@renderer/stores/settings'
import { toast } from '@renderer/stores/toast'
import { api } from '@renderer/api/client'
import { cn } from '@renderer/lib/utils'
import type {
  AppSettings,
  EmbeddingProviderName,
  EmbeddingRebuildResult,
  EmbeddingStatus,
  ProviderName
} from '@renderer/types'

const PROVIDERS: { name: ProviderName; label: string; keyHint: string; modelHint: string }[] = [
  { name: 'deepseek', label: 'DeepSeek', keyHint: 'sk-…', modelHint: 'deepseek-chat' },
  { name: 'glm', label: 'GLM（智谱）', keyHint: '…xxx.Sxxxx', modelHint: 'glm-4-flash' },
  {
    name: 'glm-coding',
    label: 'GLM 编程套餐',
    keyHint: '…xxx.Sxxxx（与智谱 API key 相同）',
    modelHint: 'glm-5.3'
  }
]

const EMBED_PROVIDERS: {
  name: EmbeddingProviderName
  label: string
  modelHint: string
}[] = [
  { name: 'glm', label: 'GLM（智谱）', modelHint: 'embedding-3' },
  { name: 'siliconflow', label: '硅基流动（bge-m3 免费）', modelHint: 'BAAI/bge-m3' }
]

export function SettingsPage(): React.JSX.Element {
  const { settings, load, update, testProvider, testStatus } = useSettingsStore()
  const [draftKeys, setDraftKeys] = useState<Record<string, string>>({})
  const [draftModel, setDraftModel] = useState('')
  const [visible, setVisible] = useState<Record<string, boolean>>({})
  const [vecStatus, setVecStatus] = useState<EmbeddingStatus | null>(null)
  const [rebuilding, setRebuilding] = useState(false)
  const [draftEmbedKey, setDraftEmbedKey] = useState('')
  const [draftMcpUrl, setDraftMcpUrl] = useState('')
  const [mcpTest, setMcpTest] = useState<{ ok: boolean; message: string } | null>(null)
  const [testingMcp, setTestingMcp] = useState(false)
  const [draftExportDir, setDraftExportDir] = useState('')

  const loadVecStatus = (): void => {
    api
      .get<EmbeddingStatus>('/embeddings/status')
      .then(setVecStatus)
      .catch(() => setVecStatus(null))
  }

  useEffect(() => {
    void load()
      .then(() => {
        const loaded = useSettingsStore.getState().settings
        if (loaded) {
          setDraftKeys(Object.fromEntries(PROVIDERS.map((p) => [p.name, ''])))
          setDraftModel(loaded.default_model)
          setDraftMcpUrl(loaded.mcp_url ?? '')
          setDraftExportDir(loaded.export_dir ?? '')
        }
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : '设置加载失败'))
    loadVecStatus()
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

        <GlassPanel className="flex items-center justify-between p-5">
          <div>
            <div className="text-sm font-medium text-zinc-200">自动记忆</div>
            <p className="mt-1 text-xs leading-5 text-zinc-500">
              开启后，Kate
              会在对话中自动记住关于你的重要事实（健康、计划、偏好），存入「记忆」合集，
              并在之后的对话中自然地想起。每条记忆保存时会有提示、可撤销，也可在知识库中管理。
            </p>
          </div>
          <ToggleSwitch
            checked={settings.memory_enabled}
            onChange={(v) => void handleSave({ memory_enabled: v })}
          />
        </GlassPanel>

        <GlassPanel className="p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
                <Layers className="size-4 text-aurora-indigo" />
                语义检索（向量）
              </div>
              <p className="mt-1 text-xs leading-5 text-zinc-500">
                开启知识库引用后，除关键词匹配外还会按语义相似度召回——换个说法提问也能找到。
                出网内容为条目标题与正文前 1500 字，发送至所选 Embedding
                服务商，与对话同属本地直连。
              </p>
            </div>
            <button
              onClick={() => {
                setRebuilding(true)
                api
                  .post<EmbeddingRebuildResult>('/embeddings/rebuild')
                  .then((result) => {
                    toast.success(`向量索引已重建（${result.indexed}/${result.total} 条）`)
                    loadVecStatus()
                  })
                  .catch((err) => toast.error(err instanceof Error ? err.message : '重建失败'))
                  .finally(() => setRebuilding(false))
              }}
              disabled={!vecStatus?.available || rebuilding}
              className="flex shrink-0 items-center gap-1 rounded-xl border border-aurora-indigo/25 bg-aurora-indigo/10 px-3 py-2 text-xs text-zinc-200 transition hover:bg-aurora-indigo/20 disabled:opacity-40"
            >
              {rebuilding ? <Spinner className="size-3.5" /> : null}
              重建索引
            </button>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <span className="text-xs text-zinc-400">Embedding 服务商</span>
            <select
              value={settings.embedding_provider}
              onChange={(e) => {
                const hint = EMBED_PROVIDERS.find((p) => p.name === e.target.value)?.modelHint
                void handleSave({
                  embedding_provider: e.target.value as EmbeddingProviderName,
                  embedding_model: hint
                }).then(() => {
                  toast.info('已切换嵌入模型——两家向量空间不互通，建议点击「重建索引」')
                  loadVecStatus()
                })
              }}
              className="glass-deep rounded-xl px-3 py-1.5 text-[13px] text-zinc-200 outline-none [&>option]:bg-ink-900"
            >
              {EMBED_PROVIDERS.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.label}
                </option>
              ))}
            </select>
            <span className="font-mono text-xs text-zinc-500">{settings.embedding_model}</span>
          </div>
          {settings.embedding_provider === 'siliconflow' && (
            <div className="mt-3 flex items-center gap-2">
              <div className="relative flex-1">
                <input
                  type="password"
                  value={draftEmbedKey}
                  onChange={(e) => setDraftEmbedKey(e.target.value)}
                  placeholder={
                    settings.embedding_api_key ? '已保存（输入以覆盖）' : '硅基流动 API Key（sk-…）'
                  }
                  className="glass-deep w-full rounded-xl px-3 py-2 font-mono text-[13px] text-zinc-200 outline-none placeholder:font-sans placeholder:text-zinc-600"
                />
              </div>
              <button
                onClick={() =>
                  void handleSave({ embedding_api_key: draftEmbedKey.trim() }).then(loadVecStatus)
                }
                disabled={!draftEmbedKey.trim()}
                className="shrink-0 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-300 transition hover:text-zinc-100 disabled:opacity-40"
              >
                保存
              </button>
            </div>
          )}
          <p className="mt-2 text-xs leading-5 text-zinc-400">
            {vecStatus === null
              ? '状态加载中…'
              : vecStatus.available
                ? `已索引 ${vecStatus.indexed} / ${vecStatus.total} 条`
                : '未启用：需先配置所选服务商的 API Key（GLM 复用上方 GLM Key，硅基流动需单独 Key）'}
          </p>
        </GlassPanel>

        <GlassPanel className="p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
            <Globe className="size-4 text-aurora-cyan" />
            外部工具（MCP）
          </div>
          <p className="mt-1 text-xs leading-5 text-zinc-500">
            填入 MCP 服务的 Streamable HTTP 端点（含 Key），Kate
            即可调用其工具获取实时数据。例如高德地图：
            <span className="font-mono text-zinc-400">https://mcp.amap.com/mcp?key=你的Key</span>
            （在高德开放平台创建「Web 服务」Key 后按其 MCP 文档拼接）。留空即停用。
          </p>
          <div className="mt-4 flex items-center gap-2">
            <input
              type="password"
              value={draftMcpUrl}
              onChange={(e) => setDraftMcpUrl(e.target.value)}
              placeholder={
                settings.mcp_url ? '已保存（输入以覆盖）' : 'MCP 端点 URL（https://…?key=…）'
              }
              className="glass-deep flex-1 rounded-xl px-3 py-2 font-mono text-[13px] text-zinc-200 outline-none placeholder:font-sans placeholder:text-zinc-600"
            />
            <button
              onClick={() => {
                void handleSave({ mcp_url: draftMcpUrl.trim() }).then(() => setMcpTest(null))
              }}
              disabled={draftMcpUrl.trim() === (settings.mcp_url ?? '')}
              className="shrink-0 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-300 transition hover:text-zinc-100 disabled:opacity-40"
            >
              保存
            </button>
            <button
              onClick={() => {
                setTestingMcp(true)
                setMcpTest(null)
                api
                  .post<{ ok: boolean; message: string }>('/mcp/test')
                  .then((r) => setMcpTest({ ok: r.ok, message: r.message }))
                  .catch((err) =>
                    setMcpTest({
                      ok: false,
                      message: err instanceof Error ? err.message : '网络错误'
                    })
                  )
                  .finally(() => setTestingMcp(false))
              }}
              disabled={!settings.mcp_url || testingMcp}
              className="flex shrink-0 items-center gap-1 rounded-xl border border-aurora-cyan/25 bg-aurora-cyan/10 px-3 py-2 text-xs text-aurora-cyan transition hover:bg-aurora-cyan/20 disabled:opacity-40"
            >
              <Plug className="size-3.5" />
              测试
            </button>
          </div>
          {(mcpTest || settings.mcp_url) && (
            <p
              className={cn(
                'mt-2 text-xs',
                mcpTest
                  ? mcpTest.ok
                    ? 'text-emerald-300/90'
                    : 'text-rose-300/90'
                  : 'text-zinc-500'
              )}
            >
              {mcpTest
                ? `${mcpTest.ok ? '✓' : '✕'} ${mcpTest.message}`
                : '已配置 MCP 端点，对话涉及景点、路线、天气时会自动调用实时查询。'}
            </p>
          )}
        </GlassPanel>

        <GlassPanel className="p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
            <FileDown className="size-4 text-aurora-indigo" />
            导出文件夹
          </div>
          <p className="mt-1 text-xs leading-5 text-zinc-500">
            对话里让 Kate「保存成文件 / 导出 md」时（如旅游行程、报告），文档会写成 独立的 Markdown
            文件存到此文件夹。留空使用默认： 文档\Kate-Cortex 导出。
          </p>
          <div className="mt-4 flex items-center gap-2">
            <input
              value={draftExportDir}
              onChange={(e) => setDraftExportDir(e.target.value)}
              placeholder={
                settings.export_dir ? '已保存（输入以覆盖）' : '默认： 文档\\Kate-Cortex 导出'
              }
              className="glass-deep flex-1 rounded-xl px-3 py-2 font-mono text-[13px] text-zinc-200 outline-none placeholder:font-sans placeholder:text-zinc-600"
            />
            <button
              onClick={() => void handleSave({ export_dir: draftExportDir.trim() })}
              disabled={draftExportDir.trim() === (settings.export_dir ?? '')}
              className="shrink-0 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-300 transition hover:text-zinc-100 disabled:opacity-40"
            >
              保存
            </button>
          </div>
          {settings.export_dir && (
            <p className="mt-2 break-all text-xs text-zinc-500">当前：{settings.export_dir}</p>
          )}
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
