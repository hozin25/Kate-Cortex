import { useEffect, useState } from 'react'
import { Bot, Pencil, Plus, Trash2 } from 'lucide-react'
import { GlassPanel } from '@renderer/components/common/Glass'
import { Spinner } from '@renderer/components/common/Badges'
import { ToggleSwitch } from '@renderer/components/common/ToggleSwitch'
import { useAgentsStore, type AgentDraft } from '@renderer/stores/agents'
import { toast } from '@renderer/stores/toast'
import { cn } from '@renderer/lib/utils'
import { PROVIDERS } from '@renderer/lib/providers'
import type { Agent } from '@renderer/types'

const EMPTY_DRAFT: AgentDraft = { name: '', description: '', prompt: '', provider: '', model: '' }

const errText = (err: unknown, fallback: string): string =>
  err instanceof Error ? err.message : fallback

interface AgentFormProps {
  draft: AgentDraft
  onChange: (draft: AgentDraft) => void
  onSubmit: () => void
  onCancel?: () => void
  busy: boolean
  submitLabel: string
}

/** 新建 / 编辑共用表单：名称 + 描述 + 提示词 + 可选指定模型（provider/model 成对） */
function AgentForm({
  draft,
  onChange,
  onSubmit,
  onCancel,
  busy,
  submitLabel
}: AgentFormProps): React.JSX.Element {
  const canSubmit = !busy && draft.name.trim().length > 0 && draft.prompt.trim().length > 0

  const pickProvider = (provider: string): void => {
    const hint = PROVIDERS.find((p) => p.name === provider)?.modelHint ?? ''
    onChange({ ...draft, provider, model: hint })
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          aria-label="Agent 名称"
          value={draft.name}
          onChange={(e) => onChange({ ...draft, name: e.target.value })}
          placeholder="名称（即 / 引用 token，如：私人生活医生）"
          className="glass-deep w-full rounded-xl px-3 py-2 text-[13px] text-zinc-200 outline-none placeholder:text-zinc-600 sm:w-56"
        />
        <input
          aria-label="Agent 描述"
          value={draft.description}
          onChange={(e) => onChange({ ...draft, description: e.target.value })}
          placeholder="一句话描述（/ 菜单里展示，可留空）"
          className="glass-deep w-full flex-1 rounded-xl px-3 py-2 text-[13px] text-zinc-200 outline-none placeholder:text-zinc-600"
        />
      </div>
      <textarea
        aria-label="Agent 提示词"
        rows={4}
        value={draft.prompt}
        onChange={(e) => onChange({ ...draft, prompt: e.target.value })}
        placeholder="角色提示词：它是谁、按什么流程回答、有哪些红线（最长 4000 字）"
        className="glass-deep w-full resize-none rounded-xl px-3 py-2 text-[13px] leading-6 text-zinc-200 outline-none placeholder:text-zinc-600"
      />
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <select
          aria-label="Agent 指定服务商"
          value={draft.provider}
          onChange={(e) => pickProvider(e.target.value)}
          className="glass-deep w-full rounded-xl px-3 py-2 text-[13px] text-zinc-200 outline-none sm:w-56 [&>option]:bg-ink-900"
        >
          <option value="">跟随会话模型</option>
          {PROVIDERS.map((p) => (
            <option key={p.name} value={p.name}>
              {p.label}
            </option>
          ))}
        </select>
        <input
          aria-label="Agent 指定模型"
          value={draft.model}
          disabled={!draft.provider}
          onChange={(e) => onChange({ ...draft, model: e.target.value })}
          placeholder={draft.provider ? '模型名（如 glm-5.3）' : '跟随会话模型'}
          className="glass-deep w-full flex-1 rounded-xl px-3 py-2 font-mono text-[13px] text-zinc-200 outline-none placeholder:font-sans placeholder:text-zinc-600 disabled:opacity-50"
        />
        <div className="flex shrink-0 gap-2">
          <button
            onClick={onSubmit}
            disabled={!canSubmit}
            className="flex flex-1 items-center justify-center gap-1 rounded-xl border border-aurora-cyan/25 bg-aurora-cyan/10 px-3 py-2 text-xs text-aurora-cyan transition hover:bg-aurora-cyan/20 disabled:opacity-40 sm:flex-none"
          >
            {busy ? <Spinner className="size-3.5" /> : <Plus className="size-3.5" />}
            {submitLabel}
          </button>
          {onCancel && (
            <button
              onClick={onCancel}
              disabled={busy}
              className="flex-1 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-300 transition hover:text-zinc-100 disabled:opacity-40 sm:flex-none"
            >
              取消
            </button>
          )}
        </div>
      </div>
      {draft.provider && (
        <p className="text-[11px] leading-4 text-zinc-600">
          指定模型仅在该 agent 被引用的那条消息生效（会话模型不变），需已配置对应 Key。
        </p>
      )}
    </div>
  )
}

export function AgentsPanel(): React.JSX.Element {
  const { agents, load, add, update, remove } = useAgentsStore()
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState<AgentDraft>(EMPTY_DRAFT)
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<AgentDraft>(EMPTY_DRAFT)
  const [savingEdit, setSavingEdit] = useState(false)

  useEffect(() => {
    load()
      .catch((err) => toast.error(errText(err, 'Agent 列表加载失败')))
      .finally(() => setLoading(false))
  }, [load])

  const submitAdd = (): void => {
    setAdding(true)
    add(draft)
      .then((agent) => {
        toast.success(`已创建 agent「${agent.name}」，聊天输入 / 即可引用`)
        setDraft(EMPTY_DRAFT)
      })
      .catch((err) => toast.error(errText(err, '创建失败')))
      .finally(() => setAdding(false))
  }

  const startEdit = (agent: Agent): void => {
    setEditingId(agent.id)
    setEditDraft({
      name: agent.name,
      description: agent.description,
      prompt: agent.prompt,
      provider: agent.provider ?? '',
      model: agent.model ?? ''
    })
  }

  const submitEdit = (): void => {
    if (!editingId) return
    setSavingEdit(true)
    update(editingId, editDraft)
      .then(() => setEditingId(null))
      .catch((err) => toast.error(errText(err, '保存失败')))
      .finally(() => setSavingEdit(false))
  }

  const toggle = (agent: Agent): void => {
    update(agent.id, { enabled: !agent.enabled }).catch((err) =>
      toast.error(errText(err, '操作失败'))
    )
  }

  const removeAgent = (agent: Agent): void => {
    if (
      !window.confirm(
        `移除 agent「${agent.name}」？历史消息里的 /${agent.name} 前缀将回落默认 Kate。`
      )
    )
      return
    remove(agent.id).catch((err) => toast.error(errText(err, '移除失败')))
  }

  return (
    <GlassPanel className="p-5">
      <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
        <Bot className="size-4 text-aurora-cyan" />
        自定义 Agent（输入 / 引用）
      </div>
      <p className="mt-1 text-xs leading-5 text-zinc-500">
        为 Kate 创建专属助手：给一段角色提示词（问诊的医生、润色的译员……），聊天输入框敲{' '}
        <span className="font-mono text-zinc-400">/</span> 选中即可让这条消息由该角色接管回答。
        知识沉淀、记忆等工具能力全部保留。
      </p>

      <div className="mt-4 space-y-3">
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Spinner className="size-3.5" />
            加载中…
          </div>
        ) : (
          agents.map((agent) =>
            editingId === agent.id ? (
              <div
                key={agent.id}
                className="rounded-xl border border-aurora-cyan/20 bg-white/[0.02] p-3"
              >
                <AgentForm
                  draft={editDraft}
                  onChange={setEditDraft}
                  onSubmit={submitEdit}
                  onCancel={() => setEditingId(null)}
                  busy={savingEdit}
                  submitLabel="保存"
                />
              </div>
            ) : (
              <div
                key={agent.id}
                className={cn(
                  'rounded-xl border border-white/[0.06] bg-white/[0.02] p-3',
                  !agent.enabled && 'opacity-55'
                )}
              >
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-[13px] text-zinc-200">
                      <span className="truncate font-mono text-aurora-cyan">/{agent.name}</span>
                      {!agent.enabled && (
                        <span className="shrink-0 rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-zinc-400">
                          已停用
                        </span>
                      )}
                      {agent.provider && agent.model && (
                        <span className="shrink-0 truncate rounded-md bg-white/[0.06] px-1.5 py-0.5 font-mono text-[10px] text-zinc-400">
                          {agent.provider} · {agent.model}
                        </span>
                      )}
                    </div>
                    {agent.description && (
                      <p className="mt-0.5 truncate text-[11px] text-zinc-500">
                        {agent.description}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button
                      onClick={() => startEdit(agent)}
                      className="grid size-7 place-items-center rounded-lg text-zinc-500 transition hover:text-zinc-200"
                      aria-label={`编辑 agent ${agent.name}`}
                    >
                      <Pencil className="size-3.5" />
                    </button>
                    <ToggleSwitch checked={agent.enabled} onChange={() => toggle(agent)} />
                    <button
                      onClick={() => removeAgent(agent)}
                      className="grid size-7 place-items-center rounded-lg text-zinc-500 transition hover:text-rose-300"
                      aria-label={`删除 agent ${agent.name}`}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            )
          )
        )}
        {!loading && agents.length === 0 && (
          <p className="text-xs text-zinc-600">还没有 agent，在下方创建第一个。</p>
        )}
      </div>

      {editingId === null && (
        <div className="mt-4 border-t border-white/[0.06] pt-4">
          <AgentForm
            draft={draft}
            onChange={setDraft}
            onSubmit={submitAdd}
            busy={adding}
            submitLabel="创建 agent"
          />
        </div>
      )}
    </GlassPanel>
  )
}
