import { create } from 'zustand'
import { api, setUnauthorizedHandler } from '@renderer/api/client'
import { isElectron } from '@renderer/lib/runtime'

export interface AuthUser {
  id: string
  username: string
  created_at: string
}

/** 单用户形态（Electron / Vercel 试用等）的占位用户：免登录直通应用 */
const LOCAL_USER: AuthUser = { id: 'local', username: 'local', created_at: '' }

interface AuthState {
  /** 当前登录用户；单用户形态恒为本地占位用户 */
  user: AuthUser | null
  /** 启动时会话检查是否完成（决定 AuthGate 渲染登录页还是应用） */
  ready: boolean
  ensureLoaded: () => Promise<void>
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string, inviteCode?: string) => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user: isElectron ? LOCAL_USER : null,
  ready: isElectron,

  ensureLoaded: async () => {
    if (isElectron) return
    try {
      // 先问后端形态：单用户部署（如 Vercel 试用）没有账号体系，免登录直通
      const health = await api.get<{ mode?: string }>('/health')
      if (health.mode !== 'multiuser') {
        set({ user: LOCAL_USER, ready: true })
        return
      }
      const user = await api.get<AuthUser>('/auth/me')
      set({ user, ready: true })
    } catch {
      set({ user: null, ready: true })
    }
  },

  login: async (username, password) => {
    const user = await api.post<AuthUser>('/auth/login', { username, password })
    set({ user, ready: true })
  },

  register: async (username, password, inviteCode) => {
    const user = await api.post<AuthUser>('/auth/register', {
      username,
      password,
      invite_code: inviteCode?.trim() || undefined
    })
    set({ user, ready: true })
  },

  logout: async () => {
    try {
      await api.post('/auth/logout')
    } finally {
      set({ user: null })
    }
  }
}))

// 会话过期：任何 API 返回 401 时清空登录态，AuthGate 随之切到登录页
setUnauthorizedHandler(() => {
  if (!isElectron) useAuthStore.setState({ user: null })
})
