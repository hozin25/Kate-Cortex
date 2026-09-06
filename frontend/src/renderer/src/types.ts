export type EntrySource = 'manual' | 'chat' | 'import'
export type ProviderName = 'deepseek' | 'glm' | 'glm-coding' | 'siliconflow' | 'modelscope'
export type EmbeddingProviderName = 'glm' | 'siliconflow'

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

export interface MemorySavedPayload {
  entry_id: string
  slug: string
  title: string
  keywords: string[]
  replaced: boolean
}

export interface MemoryRefItem {
  entry_id: string
  title: string
  content: string
  keywords: string[]
  created_at: string
}

export interface MemoryRefPayload {
  query: string
  memories: MemoryRefItem[]
}

export interface AppSettings {
  provider_keys: Record<string, string>
  default_provider: ProviderName
  default_model: string
  rag_default: boolean
  memory_enabled: boolean
  vault_path: string | null
  embedding_provider: EmbeddingProviderName
  embedding_model: string
  embedding_api_key: string | null
  mcp_url: string | null
  export_dir: string | null
}

export interface EmbeddingStatus {
  available: boolean
  indexed: number
  total: number
}

export interface EmbeddingRebuildResult {
  indexed: number
  total: number
  failed: number
}

export type ProjectionMethod = 'tsne' | 'pca' | 'insufficient' | 'unavailable'

export interface ProjectionPoint {
  entry_id: string
  title: string
  collections: string[]
  source: string
  x: number
  y: number
  z: number
}

export interface Projection {
  available: boolean
  method: ProjectionMethod
  n: number
  computed_ms: number
  points: ProjectionPoint[]
}
