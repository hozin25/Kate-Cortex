import { create } from 'zustand'
import { api } from '@renderer/api/client'
import { postSse } from '@renderer/api/sse'
import { toast } from '@renderer/stores/toast'
import type {
  AppSettings,
  ChatMessage,
  ChatSession,
  Citation,
  MemoryRefItem,
  MemorySavedPayload,
  ProviderName,
  SavedPayload,
  SuggestPayload
} from '@renderer/types'

/** 新会话起始服务商的回退顺序（设置页展示顺序） */
const START_FALLBACK_ORDER: ProviderName[] = [
  'glm',
  'siliconflow',
  'modelscope',
  'glm-coding',
  'deepseek'
]

/** 默认服务商没配 key 时回退到任一已配置的服务商——
 *  避免只填了「GLM 编程套餐」却在默认「GLM（智谱）」上报「未配置 key」 */
export function pickStartProvider(settings: AppSettings | null | undefined): ProviderName {
  const preferred = settings?.default_provider
  const keys = settings?.provider_keys ?? {}
  if (preferred && keys[preferred]) return preferred
  const fallback = START_FALLBACK_ORDER.find((p) => keys[p])
  return fallback ?? preferred ?? 'deepseek'
}

interface ChatState {
  sessions: ChatSession[]
  currentId: string | null
  messages: ChatMessage[]
  streaming: boolean
  streamText: string
  citations: Citation[]
  savedCards: SavedPayload[]
  suggestCards: SuggestPayload[]
  memoryCards: MemorySavedPayload[]
  memoryRefs: MemoryRefItem[]
  error: string | null
  abort: AbortController | null
  ragEnabled: boolean | null

  loadSessions: () => Promise<void>
  selectSession: (id: string | null) => Promise<void>
  createSession: (provider: ProviderName) => Promise<void>
  switchModel: (provider: ProviderName, model: string) => Promise<void>
  renameSession: (id: string, title: string) => Promise<void>
  removeSession: (id: string) => Promise<void>
  sendMessage: (content: string, images?: string[]) => Promise<void>
  regenerate: () => Promise<void>
  editMessage: (messageId: string, content: string) => Promise<void>
  deleteMessage: (messageId: string) => Promise<void>
  stopStreaming: () => void
  dismissSuggest: (index: number) => void
  undoMemory: (entryId: string) => Promise<void>
  clearError: () => void
}

export const useChatStore = create<ChatState>((set, get) => {
  /** chat / regenerate / resend 共用的 SSE 流处理：事件分发 + 收尾刷新 */
  const runStream = async (path: string, body: unknown): Promise<void> => {
    const controller = new AbortController()
    set({ abort: controller })

    await postSse(path, body, {
      onEvent: (event, data) => {
        const s = get()
        if (event === 'delta') {
          set({ streamText: s.streamText + String(data.text ?? '') })
        } else if (event === 'citations') {
          set({ citations: (data.entries as Citation[]) ?? [] })
        } else if (event === 'tool_result') {
          set({ savedCards: [...s.savedCards, data as unknown as SavedPayload] })
        } else if (event === 'suggest') {
          set({ suggestCards: [...s.suggestCards, data as unknown as SuggestPayload] })
        } else if (event === 'memory_saved') {
          set({ memoryCards: [...s.memoryCards, data as unknown as MemorySavedPayload] })
        } else if (event === 'memory_refs') {
          set({ memoryRefs: (data.memories as MemoryRefItem[]) ?? [] })
        } else if (event === 'mcp_notice') {
          toast.warning(String(data.message ?? '外部工具服务异常'))
        } else if (event === 'mcp_changed') {
          // 会话内 install_mcp / remove_mcp 的结果提示
          const ok = data.ok !== false
          const message = String(data.message ?? 'MCP 服务已更新')
          if (ok) toast.success(message)
          else toast.warning(message)
        } else if (event === 'file_saved') {
          toast.success(`已导出 Markdown 文件：${String(data.file_path ?? '')}`)
        } else if (event === 'done') {
          set({ streamText: '' })
        } else if (event === 'error') {
          set({ error: String(data.message ?? '未知错误'), streamText: '' })
        }
      },
      onError: (message) => set({ error: message, streamText: '' })
    }).catch((err) => {
      if (!(err instanceof DOMException && err.name === 'AbortError')) {
        set({ error: err instanceof Error ? err.message : String(err), streamText: '' })
      }
    })

    set({ streaming: false, abort: null })

    const id = get().currentId
    if (id && !controller.signal.aborted) {
      const [messages, sessions] = await Promise.all([
        api.get<ChatMessage[]>(`/chat/sessions/${id}/messages`),
        api.get<ChatSession[]>('/chat/sessions')
      ])
      if (get().currentId === id) set({ messages, sessions })
    }
  }

  const beginStream = (): boolean => {
    const { currentId, streaming } = get()
    if (!currentId || streaming) return false
    set({ streaming: true, streamText: '', citations: [], memoryRefs: [], error: null })
    return true
  }

  return {
    sessions: [],
    currentId: null,
    messages: [],
    streaming: false,
    streamText: '',
    citations: [],
    savedCards: [],
    suggestCards: [],
    memoryCards: [],
    memoryRefs: [],
    error: null,
    abort: null,
    ragEnabled: null,

    loadSessions: async () => {
      const sessions = await api.get<ChatSession[]>('/chat/sessions')
      set({ sessions })
    },

    selectSession: async (id) => {
      get().abort?.abort()
      set({
        currentId: id,
        messages: [],
        citations: [],
        savedCards: [],
        suggestCards: [],
        memoryCards: [],
        memoryRefs: [],
        streamText: '',
        streaming: false,
        error: null
      })
      if (!id) return
      const messages = await api.get<ChatMessage[]>(`/chat/sessions/${id}/messages`)
      if (get().currentId !== id) return
      set({ messages })
    },

    createSession: async (provider) => {
      const session = await api.post<ChatSession>('/chat/sessions', { provider })
      set({
        sessions: [session, ...get().sessions],
        currentId: session.id,
        messages: [],
        citations: [],
        savedCards: [],
        suggestCards: [],
        memoryCards: [],
        memoryRefs: [],
        streamText: '',
        error: null
      })
    },

    renameSession: async (id, title) => {
      const updated = await api.patch<ChatSession>(`/chat/sessions/${id}`, { title })
      set({ sessions: get().sessions.map((s) => (s.id === id ? updated : s)) })
    },

    switchModel: async (provider, model) => {
      const { currentId } = get()
      if (!currentId) return
      const updated = await api.patch<ChatSession>(`/chat/sessions/${currentId}`, {
        provider,
        model
      })
      set({ sessions: get().sessions.map((s) => (s.id === updated.id ? updated : s)) })
    },

    removeSession: async (id) => {
      await api.delete(`/chat/sessions/${id}`)
      const sessions = get().sessions.filter((s) => s.id !== id)
      const wasCurrent = get().currentId === id
      set({
        sessions,
        ...(wasCurrent
          ? {
              currentId: null,
              messages: [],
              savedCards: [],
              suggestCards: [],
              memoryCards: [],
              memoryRefs: [],
              citations: []
            }
          : {})
      })
    },

    sendMessage: async (content, images = []) => {
      const { currentId } = get()
      if (!beginStream()) return
      // 乐观渲染：本地先用 data URL 直出图片，SSE 完成后以服务端消息（附件路径）替换
      const imageMd = images.map((url) => `![图片](${url})`).join('\n')
      const userMsg: ChatMessage = {
        id: `local_${Date.now()}`,
        conversation_id: currentId!,
        role: 'user',
        content: imageMd ? `${content}\n\n${imageMd}` : content,
        tool_calls: null,
        knowledge_refs: null,
        created_at: new Date().toISOString()
      }
      set({ messages: [...get().messages, userMsg] })

      await runStream(`/chat/sessions/${currentId}/chat`, {
        content,
        rag_enabled: get().ragEnabled,
        images
      })
    },

    regenerate: async () => {
      const { currentId, messages } = get()
      if (!beginStream()) return
      // 乐观截断：移除最后一条用户消息之后的回复（done 后整体刷新校正）
      let lastUserIdx = -1
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === 'user') {
          lastUserIdx = i
          break
        }
      }
      if (lastUserIdx < 0) {
        set({ streaming: false, error: '没有可重新生成的消息' })
        return
      }
      set({ messages: messages.slice(0, lastUserIdx + 1) })

      await runStream(`/chat/sessions/${currentId}/regenerate`, {
        rag_enabled: get().ragEnabled
      })
    },

    editMessage: async (messageId, content) => {
      const { currentId, messages } = get()
      if (!beginStream()) return
      const idx = messages.findIndex((m) => m.id === messageId)
      if (idx < 0 || messages[idx].role !== 'user' || messageId.startsWith('local_')) {
        set({ streaming: false })
        return
      }
      // 乐观更新：保留图片引用（后端 keep_images 同规则），其后截断
      const imageRefs = messages[idx].content.match(/!\[[^\]]*\]\(attachments\/[^)]+\)/g)
      const imageMd = imageRefs?.join('\n')
      set({
        messages: [
          ...messages.slice(0, idx),
          {
            ...messages[idx],
            content: imageMd ? `${content}\n\n${imageMd}` : content
          }
        ]
      })

      await runStream(`/chat/sessions/${currentId}/messages/${messageId}/resend`, {
        content,
        keep_images: true,
        rag_enabled: get().ragEnabled
      })
    },

    deleteMessage: async (messageId) => {
      const { currentId } = get()
      if (!currentId || messageId.startsWith('local_')) return
      try {
        await api.delete(`/chat/sessions/${currentId}/messages/${messageId}`)
        set({ messages: get().messages.filter((m) => m.id !== messageId) })
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '删除失败')
      }
    },

    stopStreaming: () => {
      get().abort?.abort()
      set({ streaming: false })
    },

    dismissSuggest: (index) => {
      set({ suggestCards: get().suggestCards.filter((_, i) => i !== index) })
    },

    undoMemory: async (entryId) => {
      try {
        await api.delete(`/entries/${entryId}`)
        set({ memoryCards: get().memoryCards.filter((c) => c.entry_id !== entryId) })
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '撤销失败')
      }
    },

    clearError: () => set({ error: null })
  }
})
