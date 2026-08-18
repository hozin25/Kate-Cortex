import { create } from 'zustand'
import { api } from '@renderer/api/client'
import type { EntryList, EntrySummary, TagCount } from '@renderer/types'

interface LibraryState {
  items: EntrySummary[]
  total: number
  tags: TagCount[]
  typeFilter: string | null
  tagFilter: string | null
  query: string
  loading: boolean
  load: () => Promise<void>
  setTypeFilter: (type: string | null) => void
  setTagFilter: (tag: string | null) => void
  setQuery: (q: string) => void
  refresh: () => Promise<void>
}

export const useLibraryStore = create<LibraryState>((set, get) => ({
  items: [],
  total: 0,
  tags: [],
  typeFilter: null,
  tagFilter: null,
  query: '',
  loading: false,

  load: async () => {
    const tags = await api.get<TagCount[]>('/tags')
    set({ tags })
    await get().refresh()
  },

  setTypeFilter: (type) => {
    set({ typeFilter: type })
    void get().refresh()
  },

  setTagFilter: (tag) => {
    set({ tagFilter: tag })
    void get().refresh()
  },

  setQuery: (q) => {
    set({ query: q })
    void get().refresh()
  },

  refresh: async () => {
    const { typeFilter, tagFilter, query } = get()
    set({ loading: true })
    try {
      const params = new URLSearchParams()
      if (typeFilter) params.set('type', typeFilter)
      if (tagFilter) params.set('tag', tagFilter)
      if (query.trim()) params.set('q', query.trim())
      const result = await api.get<EntryList>(`/entries?${params.toString()}`)
      set({ items: result.items, total: result.total })
    } finally {
      set({ loading: false })
    }
  }
}))
