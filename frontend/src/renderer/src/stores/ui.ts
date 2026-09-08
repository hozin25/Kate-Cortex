import { create } from 'zustand'

interface UiState {
  /** 移动端会话抽屉（<md 屏幕没有左侧栏，从对话页头部唤出） */
  sessionsOpen: boolean
  setSessionsOpen: (open: boolean) => void
}

export const useUiStore = create<UiState>((set) => ({
  sessionsOpen: false,
  setSessionsOpen: (open) => set({ sessionsOpen: open })
}))
