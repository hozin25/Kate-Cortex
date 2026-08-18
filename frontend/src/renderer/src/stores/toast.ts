import { create } from 'zustand'

export interface Toast {
  id: number
  kind: 'error' | 'success' | 'info'
  message: string
}

interface ToastState {
  toasts: Toast[]
  push: (kind: Toast['kind'], message: string) => void
  dismiss: (id: number) => void
}

let nextId = 1

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  push: (kind, message) => {
    const id = nextId++
    set({ toasts: [...get().toasts, { id, kind, message }] })
    setTimeout(() => get().dismiss(id), kind === 'error' ? 6000 : 3200)
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) })
}))

export const toast = {
  error: (message: string): void => useToastStore.getState().push('error', message),
  success: (message: string): void => useToastStore.getState().push('success', message),
  info: (message: string): void => useToastStore.getState().push('info', message)
}
