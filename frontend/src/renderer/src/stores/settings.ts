import { create } from 'zustand'
import { api, apiUrl } from '@renderer/api/client'
import type { AppSettings, ProviderName } from '@renderer/types'

interface SettingsState {
  settings: AppSettings | null
  loading: boolean
  saving: boolean
  testStatus: Record<string, { ok: boolean; message: string } | null>
  load: () => Promise<void>
  update: (
    patch: Partial<Omit<AppSettings, 'provider_keys'>> & { provider_keys?: Record<string, string> }
  ) => Promise<void>
  testProvider: (provider: ProviderName) => Promise<void>
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  settings: null,
  loading: false,
  saving: false,
  testStatus: {},

  load: async () => {
    set({ loading: true })
    try {
      const settings = await api.get<AppSettings>('/settings')
      set({ settings })
    } finally {
      set({ loading: false })
    }
  },

  update: async (patch) => {
    set({ saving: true })
    try {
      const settings = await api.put<AppSettings>('/settings', patch)
      set({ settings })
    } finally {
      set({ saving: false })
    }
  },

  testProvider: async (provider) => {
    set({ testStatus: { ...get().testStatus, [provider]: null } })
    let result: { ok: boolean; message: string }
    try {
      const resp = await fetch(apiUrl('/providers/test'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider })
      })
      const body = await resp.json()
      result =
        resp.ok && body?.ok
          ? { ok: true, message: `连通正常（${body.reply ?? ''}）` }
          : { ok: false, message: String(body?.detail ?? `HTTP ${resp.status}`) }
    } catch (err) {
      result = { ok: false, message: err instanceof Error ? err.message : '网络错误' }
    }
    set({ testStatus: { ...get().testStatus, [provider]: result } })
  }
}))
