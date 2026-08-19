export type EntrySource = 'manual' | 'chat' | 'import'
export type ProviderName = 'deepseek' | 'glm'

export interface EntrySummary {
  id: string
  slug: string
  title: string
  collections: string[]
  source: string
  language: string | null
  conversation_id: string | null
  created_at: string
  updated_at: string
}

export interface Entry extends EntrySummary {
  content: string
  file_path: string
}

export interface EntryList {
  items: EntrySummary[]
  total: number
}

export interface CollectionCount {
  name: string
  count: number
}

export interface ChatSession {
  id: string
  title: string | null
  provider: string
  model: string
  created_at: string
  updated_at: string
  preview: string
}

export interface ChatMessage {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  tool_calls: ToolCallSummary[] | null
  knowledge_refs: string[] | null
  created_at: string
}

export interface ToolCallSummary {
  id: string
  function: { name: string; arguments: string }
}

export interface Citation {
  id: string
  title: string
  slug: string
}

export interface SavedPayload {
  entry_id: string
  slug: string
  title: string
  collections: string[]
}

export interface SuggestPayload {
  title: string
  collections: string[]
  preview: string
}

export interface AppSettings {
  provider_keys: Record<string, string>
  default_provider: ProviderName
  default_model: string
  rag_default: boolean
  vault_path: string | null
}
