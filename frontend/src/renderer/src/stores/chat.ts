import { create } from 'zustand'
import { api } from '@renderer/api/client'
import { postSse } from '@renderer/api/sse'
import { toast } from '@renderer/stores/toast'
import type {
  ChatMessage,
  ChatSession,
  Citation,
  MemoryRefItem,
  MemorySavedPayload,
  ProviderName,
  SavedPayload,
  SuggestPayload
} from '@renderer/types'

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
  renameSession: (id: string, title: string) => Promise<void>
  removeSession: (id: string) => Promise<void>
  sendMessage: (content: string, images?: string[]) => Promise<void>
  stopStreaming: () => void
  dismissSuggest: (index: number) => void
  undoMemory: (entryId: string) => Promise<void>
  clearError: () => void
}

export const useChatStore = create<ChatState>((set, get) => ({
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
    const { currentId, streaming } = get()
    if (!currentId || streaming) return
    // 乐观渲染：本地先用 data URL 直出图片，SSE 完成后以服务端消息（附件路径）替换
    const imageMd = images.map((url) => `![图片](${url})`).join('\n')
    const userMsg: ChatMessage = {
      id: `local_${Date.now()}`,
      conversation_id: currentId,
      role: 'user',
      content: imageMd ? `${content}\n\n${imageMd}` : content,
      tool_calls: null,
      knowledge_refs: null,
      created_at: new Date().toISOString()
    }
    set({
      messages: [...get().messages, userMsg],
      streaming: true,
      streamText: '',
      citations: [],
      memoryRefs: [],
      error: null
    })

    const controller = new AbortController()
    set({ abort: controller })

    await postSse(
      `/chat/sessions/${currentId}/chat`,
      { content, rag_enabled: get().ragEnabled, images },
      {
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
          } else if (event === 'file_saved') {
            toast.success(`已导出 Markdown 文件：${String(data.file_path ?? '')}`)
          } else if (event === 'done') {
            set({ streamText: '' })
          } else if (event === 'error') {
            set({ error: String(data.message ?? '未知错误'), streamText: '' })
          }
        },
        onError: (message) => set({ error: message, streamText: '' })
      },
      controller.signal
    ).catch((err) => {
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
}))
