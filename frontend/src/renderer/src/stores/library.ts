import { create } from 'zustand'
import { api } from '@renderer/api/client'
import type { CollectionCount, EntryList, EntrySummary } from '@renderer/types'

interface LibraryState {
  items: EntrySummary[]
  total: number
  collections: CollectionCount[]
  collectionFilter: string | null
  query: string
  loading: boolean
  load: () => Promise<void>
  setCollectionFilter: (collection: string | null) => void
  setQuery: (q: string) => void
  createCollection: (name: string) => Promise<void>
  renameCollection: (oldName: string, newName: string) => Promise<void>
  deleteCollection: (name: string) => Promise<void>
  refresh: () => Promise<void>
}

export const useLibraryStore = create<LibraryState>((set, get) => ({
  items: [],
  total: 0,
  collections: [],
  collectionFilter: null,
  query: '',
  loading: false,

  load: async () => {
    const collections = await api.get<CollectionCount[]>('/collections')
    set({ collections })
    await get().refresh()
  },

  setCollectionFilter: (collection) => {
    set({ collectionFilter: collection })
    void get().refresh()
  },

  setQuery: (q) => {
    set({ query: q })
    void get().refresh()
  },

  createCollection: async (name) => {
    await api.post('/collections', { name })
    const collections = await api.get<CollectionCount[]>('/collections')
    set({ collections })
  },

  renameCollection: async (oldName, newName) => {
    await api.put(`/collections/${encodeURIComponent(oldName)}`, { name: newName })
    await get().load()
  },

  deleteCollection: async (name) => {
    await api.delete(`/collections/${encodeURIComponent(name)}`)
    const { collectionFilter } = get()
    if (collectionFilter === name) {
      set({ collectionFilter: null })
    }
    await get().load()
  },

  refresh: async () => {
    const { collectionFilter, query } = get()
    set({ loading: true })
    try {
      const params = new URLSearchParams()
      if (collectionFilter) params.set('collection', collectionFilter)
      if (query.trim()) params.set('q', query.trim())
      const result = await api.get<EntryList>(`/entries?${params.toString()}`)
      set({ items: result.items, total: result.total })
    } finally {
      set({ loading: false })
    }
  }
}))
