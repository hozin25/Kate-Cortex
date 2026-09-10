import { useEffect, useState } from 'react'
import {
  Eye,
  EyeOff,
  FileDown,
  FolderInput,
  Globe,
  KeyRound,
  Layers,
  Plug,
  Settings2
} from 'lucide-react'
import { GlassPanel } from '@renderer/components/common/Glass'
import { Spinner } from '@renderer/components/common/Badges'
import { useSettingsStore } from '@renderer/stores/settings'
import { toast } from '@renderer/stores/toast'
import { api } from '@renderer/api/client'
import { cn } from '@renderer/lib/utils'
import { getTheme, setTheme, type Theme } from '@renderer/lib/theme'
import type {
  AppSettings,
  EmbeddingProviderName,
  EmbeddingRebuildResult,
  EmbeddingStatus,
  ProviderName
} from '@renderer/types'

const PROVIDERS: { name: ProviderName; label: string; keyHint: string; modelHint: string }[] = [
  { name: 'glm', label: 'GLM（智谱）', keyHint: '…xxx.Sxxxx', modelHint: 'glm-4.7-flash' },
  {
    name: 'siliconflow',
    label: '硅基流动（免费档）',
    keyHint: 'sk-…',
    modelHint: 'Qwen/Qwen3-8B'
  },
  {
    name: 'modelscope',
    label: '魔搭 ModelScope（每日 2000 次免费）',
    keyHint: 'ms-…',
    modelHint: 'Qwen/Qwen3-235B-A22B-Instruct-2507'
  },
  { name: 'deepseek', label: 'DeepSeek', keyHint: 'sk-…', modelHint: 'deepseek-chat' },
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

/** 内核是否支持 -webkit-text-security（Chromium/WebKit 支持，Firefox 不支持） */
const TEXT_SECURITY_OK =
  typeof CSS !== 'undefined' &&
  typeof CSS.supports === 'function' &&
  CSS.supports('-webkit-text-security', 'disc')

interface SecretInputProps {
  value: string
  onChange: (value: string) => void
  placeholder: string
  visible: boolean
  onToggleVisible?: () => void
  className?: string
}

/** 密钥输入框：默认用文本框 + CSS 掩码显示圆点，而非 type=password——
 *  部分国产浏览器内核对 password 输入框长按只弹「自动填充」没有「粘贴」；
 *  不支持掩码属性的内核（Firefox）回落 type=password。 */
function SecretInput({
  value,
  onChange,
  placeholder,
  visible,
  onToggleVisible,
  className
}: SecretInputProps): React.JSX.Element {
  return (
    <div className={cn('relative', className)}>
      <input
        type={TEXT_SECURITY_OK ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        className={cn(
          'glass-deep w-full rounded-xl px-3 py-2 font-mono text-[13px] text-zinc-200 outline-none placeholder:font-sans placeholder:text-zinc-600',
          TEXT_SECURITY_OK && !visible && 'kc-masked',
          onToggleVisible && 'pr-9'
        )}
      />
      {onToggleVisible && (
        <button
          onClick={onToggleVisible}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
          aria-label="显示/隐藏"
        >
          {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      )}
    </div>
  )
}

export function SettingsPage(): React.JSX.Element {
  const { settings, load, update, testProvider, testStatus } = useSettingsStore()
  const [draftKeys, setDraftKeys] = useState<Record<string, string>>({})
  const [draftModel, setDraftModel] = useState('')
  const [visible, setVisible] = useState<Record<string, boolean>>({})
  const [embedKeyVisible, setEmbedKeyVisible] = useState(false)
  const [mcpVisible, setMcpVisible] = useState(false)
  const [vecStatus, setVecStatus] = useState<EmbeddingStatus | null>(null)
  const [rebuilding, setRebuilding] = useState(false)
  const [draftEmbedKey, setDraftEmbedKey] = useState('')
  const [draftMcpUrl, setDraftMcpUrl] = useState('')
  const [mcpTest, setMcpTest] = useState<{ ok: boolean; message: string } | null>(null)
  const [testingMcp, setTestingMcp] = useState(false)
  const [draftExportDir, setDraftExportDir] = useState('')
  const [theme, setThemeState] = useState<Theme>(getTheme())
  const [draftObsidianDir, setDraftObsidianDir] = useState('')
  const [draftVaultDir, setDraftVaultDir] = useState('')
  const [importing, setImporting] = useState<
    'obsidian-preview' | 'obsidian-run' | 'vault-preview' | 'vault-run' | null
  >(null)
  const [importReport, setImportReport] = useState<Record<string, unknown> | null>(null)

  const runImport = (kind: 'obsidian' | 'vault', dryRun: boolean): Promise<void> => {
    const source_dir = (kind === 'obsidian' ? draftObsidianDir : draftVaultDir).trim()
    setImporting(`${kind}-${dryRun ? 'preview' : 'run'}`)
    setImportReport(null)
    return api
      .post<Record<string, unknown>>(`/import/${kind}`, { source_dir, dry_run: dryRun })
      .then((report) => {
        setImportReport(report)
        if (!dryRun) {
          const attachments = (report.attachments as number) ?? 0
          toast.success(
            `导入完成：${(report.imported as number) ?? 0} 条条目` +
              (attachments > 0 ? `、${attachments} 个附件` : '')
          )
        } else {
          toast.info('预览完成，报告见下方')
        }
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : '导入失败'))
      .finally(() => setImporting(null))
  }

  const handleTheme = (next: Theme): void => {
    setTheme(next)
    setThemeState(next)
  }

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
    <div className="h-full overflow-y-auto px-4 py-4 sm:px-8 sm:py-6">
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <h1 className="font-display text-lg text-zinc-100">设置</h1>

        <GlassPanel className="flex items-center justify-between p-5">
          <div>
            <div className="text-sm font-medium text-zinc-200">外观</div>
            <p className="mt-1 text-xs leading-5 text-zinc-500">
              亮色 / 暗色主题，选择即时生效并保存在本机。
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1 rounded-xl border border-white/[0.06] bg-white/[0.03] p-1">
            <ThemeOption
              active={theme === 'dark'}
              onClick={() => handleTheme('dark')}
              label="暗色"
            />
            <ThemeOption
              active={theme === 'light'}
              onClick={() => handleTheme('light')}
              label="亮色"
            />
          </div>
        </GlassPanel>

        <GlassPanel className="p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
            <KeyRound className="size-4 text-aurora-cyan" />
            API Key
          </div>
          <p className="mt-1 text-xs leading-5 text-zinc-500">
            Key 保存在本地 SQLite，仅用于从本机直连对应服务商。填写后点击「测试」验证连通。
          </p>
          <p className="mt-1 text-xs leading-5 text-zinc-500">
            免费组合推荐：对话用 GLM（glm-4.7-flash 完全免费）或硅基流动（Qwen3-8B
            免费档），语义检索用下方硅基流动 bge-m3（免费）——全程零成本。
          </p>
          <div className="mt-4 space-y-4">
            {PROVIDERS.map((p) => {
              const stored = settings.provider_keys[p.name]
              const status = testStatus[p.name]
              return (
                <div key={p.name}>
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-2">
                    <span className="shrink-0 text-[13px] text-zinc-300 sm:w-24">{p.label}</span>
                    <SecretInput
                      className="w-full flex-1"
                      value={draftKeys[p.name] ?? ''}
                      onChange={(v) => setDraftKeys({ ...draftKeys, [p.name]: v })}
                      placeholder={stored ? '已保存（输入以覆盖）' : p.keyHint}
                      visible={visible[p.name] ?? false}
                      onToggleVisible={() =>
                        setVisible({ ...visible, [p.name]: !visible[p.name] })
                      }
                    />
                    <div className="flex gap-2 sm:contents">
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
                        className="flex-1 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-300 transition hover:text-zinc-100 disabled:opacity-40 sm:flex-none"
                      >
                        保存
                      </button>
                      <button
                        onClick={() => void testProvider(p.name)}
                        disabled={!stored && !keyChanged(p.name)}
                        className="flex flex-1 items-center justify-center gap-1 rounded-xl border border-aurora-cyan/25 bg-aurora-cyan/10 px-3 py-2 text-xs text-aurora-cyan transition hover:bg-aurora-cyan/20 disabled:opacity-40 sm:flex-none"
                      >
                        <Plug className="size-3.5" />
                        测试
                      </button>
                    </div>
                  </div>
                  {status && (
                    <p
                      className={cn(
                        'mt-1.5 text-xs sm:pl-26',
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
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-2">
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
              className="glass-deep w-full rounded-xl px-3 py-2 text-[13px] text-zinc-200 outline-none sm:w-auto [&>option]:bg-ink-900"
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
              className="glass-deep w-full flex-1 rounded-xl px-3 py-2 font-mono text-[13px] text-zinc-200 outline-none placeholder:text-zinc-600"
            />
            <button
              onClick={() => void handleSave({ default_model: draftModel.trim() })}
              disabled={draftModel.trim() === settings.default_model || !draftModel.trim()}
              className="w-full shrink-0 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-300 transition hover:text-zinc-100 disabled:opacity-40 sm:w-auto"
            >
              保存
            </button>
          </div>
        </GlassPanel>

        <GlassPanel className="p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0 text-sm font-medium text-zinc-200">
              知识库引用（RAG）默认开关
            </div>
            <ToggleSwitch
              checked={settings.rag_default}
              onChange={(v) => void handleSave({ rag_default: v })}
            />
          </div>
          <p className="mt-1 text-xs leading-5 text-zinc-500">
            开启后，新对话提问时 Kate 会自动检索知识库相关条目作为回答参考。对话中可单独切换。
          </p>
        </GlassPanel>

        <GlassPanel className="p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0 text-sm font-medium text-zinc-200">自动记忆</div>
            <ToggleSwitch
              checked={settings.memory_enabled}
              onChange={(v) => void handleSave({ memory_enabled: v })}
            />
          </div>
          <p className="mt-1 text-xs leading-5 text-zinc-500">
            开启后，Kate
            会在对话中自动记住关于你的重要事实（健康、计划、偏好），存入「记忆」合集，
            并在之后的对话中自然地想起。每条记忆保存时会有提示、可撤销，也可在知识库中管理。
          </p>
        </GlassPanel>

        <GlassPanel className="p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
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
              className="flex w-fit shrink-0 items-center gap-1 self-start rounded-xl border border-aurora-indigo/25 bg-aurora-indigo/10 px-3 py-2 text-xs text-zinc-200 transition hover:bg-aurora-indigo/20 disabled:opacity-40 sm:self-auto"
            >
              {rebuilding ? <Spinner className="size-3.5" /> : null}
              重建索引
            </button>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
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
              className="glass-deep max-w-full rounded-xl px-3 py-1.5 text-[13px] text-zinc-200 outline-none [&>option]:bg-ink-900"
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
            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-2">
              <SecretInput
                className="w-full flex-1"
                value={draftEmbedKey}
                onChange={setDraftEmbedKey}
                placeholder={
                  settings.embedding_api_key ? '已保存（输入以覆盖）' : '硅基流动 API Key（sk-…）'
                }
                visible={embedKeyVisible}
                onToggleVisible={() => setEmbedKeyVisible(!embedKeyVisible)}
              />
              <button
                onClick={() =>
                  void handleSave({ embedding_api_key: draftEmbedKey.trim() }).then(loadVecStatus)
                }
                disabled={!draftEmbedKey.trim()}
                className="w-full shrink-0 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-300 transition hover:text-zinc-100 disabled:opacity-40 sm:w-auto"
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
          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-2">
            <SecretInput
              className="w-full flex-1"
              value={draftMcpUrl}
              onChange={setDraftMcpUrl}
              placeholder={
                settings.mcp_url ? '已保存（输入以覆盖）' : 'MCP 端点 URL（https://…?key=…）'
              }
              visible={mcpVisible}
              onToggleVisible={() => setMcpVisible(!mcpVisible)}
            />
            <div className="flex gap-2 sm:contents">
              <button
                onClick={() => {
                  void handleSave({ mcp_url: draftMcpUrl.trim() }).then(() => setMcpTest(null))
                }}
                disabled={draftMcpUrl.trim() === (settings.mcp_url ?? '')}
                className="flex-1 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-300 transition hover:text-zinc-100 disabled:opacity-40 sm:flex-none"
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
                className="flex flex-1 items-center justify-center gap-1 rounded-xl border border-aurora-cyan/25 bg-aurora-cyan/10 px-3 py-2 text-xs text-aurora-cyan transition hover:bg-aurora-cyan/20 disabled:opacity-40 sm:flex-none"
              >
                <Plug className="size-3.5" />
                测试
              </button>
            </div>
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
          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-2">
            <input
              value={draftExportDir}
              onChange={(e) => setDraftExportDir(e.target.value)}
              placeholder={
                settings.export_dir ? '已保存（输入以覆盖）' : '默认： 文档\\Kate-Cortex 导出'
              }
              className="glass-deep w-full flex-1 rounded-xl px-3 py-2 font-mono text-[13px] text-zinc-200 outline-none placeholder:font-sans placeholder:text-zinc-600"
            />
            <button
              onClick={() => void handleSave({ export_dir: draftExportDir.trim() })}
              disabled={draftExportDir.trim() === (settings.export_dir ?? '')}
              className="w-full shrink-0 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-300 transition hover:text-zinc-100 disabled:opacity-40 sm:w-auto"
            >
              保存
            </button>
          </div>
          {settings.export_dir && (
            <p className="mt-2 break-all text-xs text-zinc-500">当前：{settings.export_dir}</p>
          )}
        </GlassPanel>

        <GlassPanel className="p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
            <FolderInput className="size-4 text-aurora-violet" />
            数据导入
          </div>
          <p className="mt-1 text-xs leading-5 text-zinc-500">
            粘贴源目录的绝对路径（MVP 不做文件夹选择对话框）。先「预览」看报告，确认后再「执行」。
            导入是复制，不会删除或修改源目录。
          </p>

          <div className="mt-4 space-y-3">
            <div>
              <div className="text-[13px] text-zinc-300">Obsidian vault</div>
              <div className="mt-1.5 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-2">
                <input
                  value={draftObsidianDir}
                  onChange={(e) => setDraftObsidianDir(e.target.value)}
                  placeholder="D:\Obsidian\MyVault"
                  className="glass-deep w-full flex-1 rounded-xl px-3 py-2 font-mono text-[13px] text-zinc-200 outline-none placeholder:font-sans placeholder:text-zinc-600"
                />
                <ImportButtons
                  disabled={!draftObsidianDir.trim() || importing !== null}
                  busy={importing === 'obsidian-preview' || importing === 'obsidian-run'}
                  onPreview={() => void runImport('obsidian', true)}
                  onRun={() => void runImport('obsidian', false)}
                />
              </div>
            </div>
            <div>
              <div className="text-[13px] text-zinc-300">Kate-Cortex vault（从另一份数据目录合并）</div>
              <div className="mt-1.5 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-2">
                <input
                  value={draftVaultDir}
                  onChange={(e) => setDraftVaultDir(e.target.value)}
                  placeholder="D:\workspace\Kate-Cortex\vault"
                  className="glass-deep w-full flex-1 rounded-xl px-3 py-2 font-mono text-[13px] text-zinc-200 outline-none placeholder:font-sans placeholder:text-zinc-600"
                />
                <ImportButtons
                  disabled={!draftVaultDir.trim() || importing !== null}
                  busy={importing === 'vault-preview' || importing === 'vault-run'}
                  onPreview={() => void runImport('vault', true)}
                  onRun={() => void runImport('vault', false)}
                />
              </div>
              <p className="mt-1 text-[11px] leading-4 text-zinc-600">
                条目/合集/双链/附件合并拷贝，同名冲突自动改名；API Key 只补缺失不覆盖。
              </p>
            </div>
            {importReport && (
              <pre className="max-h-56 overflow-auto rounded-xl bg-white/[0.04] p-3 font-mono text-[11px] leading-5 text-zinc-300">
                {JSON.stringify(importReport, null, 2)}
              </pre>
            )}
          </div>
        </GlassPanel>

        <GlassPanel className="p-5">
          <div className="text-sm font-medium text-zinc-200">Vault 路径（启动时确定）</div>
          <p className="mt-1 break-all font-mono text-xs leading-5 text-zinc-500">
            {settings.vault_path ?? '（使用默认路径）'}
          </p>
          <p className="mt-2 text-[11px] leading-4 text-zinc-600">
            所有笔记以 Markdown 文件存于此目录，可直接用任意编辑器打开。路径由环境变量
            KATE_VAULT_PATH / KATE_DB_PATH 或默认位置决定，不支持在界面内修改。
          </p>
        </GlassPanel>
      </div>
    </div>
  )
}

interface ImportButtonsProps {
  disabled: boolean
  busy: boolean
  onPreview: () => void
  onRun: () => void
}

function ImportButtons({ disabled, busy, onPreview, onRun }: ImportButtonsProps): React.JSX.Element {
  return (
    <div className="flex gap-2 sm:contents">
      <button
        onClick={onPreview}
        disabled={disabled || busy}
        className="flex-1 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-300 transition hover:text-zinc-100 disabled:opacity-40 sm:flex-none"
      >
        预览
      </button>
      <button
        onClick={onRun}
        disabled={disabled || busy}
        className="flex flex-1 items-center justify-center gap-1 rounded-xl border border-aurora-violet/30 bg-aurora-violet/15 px-3 py-2 text-xs text-zinc-200 transition hover:brightness-125 disabled:opacity-40 sm:flex-none"
      >
        {busy ? <Spinner className="size-3.5" /> : null}
        执行
      </button>
    </div>
  )
}

interface ThemeOptionProps {
  active: boolean
  onClick: () => void
  label: string
}

function ThemeOption({ active, onClick, label }: ThemeOptionProps): React.JSX.Element {
  return (
    <button
      onClick={onClick}
      className={cn(
        'whitespace-nowrap rounded-lg px-3 py-1.5 text-xs transition',
        active
          ? 'bg-aurora-indigo/20 text-zinc-100 shadow-[inset_0_0_0_1px] shadow-aurora-indigo/25'
          : 'text-zinc-500 hover:text-zinc-300'
      )}
    >
      {label}
    </button>
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
