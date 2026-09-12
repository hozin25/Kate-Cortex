import { create } from 'zustand'
import { api } from '@renderer/api/client'
import type { Agent } from '@renderer/types'

/** 新建 / 编辑共用的表单载荷（provider 为空串视为不指定模型） */
export interface AgentDraft {
  name: string
  description: string
  prompt: string
  provider: string
  model: string
}

interface AgentsState {
  agents: Agent[]
  loaded: boolean
  load: () => Promise<void>
  add: (draft: AgentDraft) => Promise<Agent>
  update: (id: string, patch: Partial<AgentDraft> & { enabled?: boolean }) => Promise<Agent>
  remove: (id: string) => Promise<void>
}

/** 聊天页 `/` 菜单与设置页 Agent 面板共用同一份，增删改后菜单即时可见 */
export const useAgentsStore = create<AgentsState>((set, get) => ({
  agents: [],
  loaded: false,

  load: async () => {
    const r = await api.get<{ agents: Agent[] }>('/agents')
    set({ agents: r.agents, loaded: true })
  },

  add: async (draft) => {
    const agent = await api.post<Agent>('/agents', {
      name: draft.name.trim(),
      description: draft.description.trim(),
      prompt: draft.prompt,
      provider: draft.provider || null,
      model: draft.model.trim() || null
    })
    set({ agents: [...get().agents, agent] })
    return agent
  },

  update: async (id, patch) => {
    const updated = await api.patch<Agent>(`/agents/${id}`, patch)
    set({ agents: get().agents.map((a) => (a.id === id ? updated : a)) })
    return updated
  },

  remove: async (id) => {
    await api.delete(`/agents/${id}`)
    set({ agents: get().agents.filter((a) => a.id !== id) })
  }
}))
