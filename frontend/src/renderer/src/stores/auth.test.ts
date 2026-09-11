import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  unauthorizedHandler: null as (() => void) | null
}))

vi.mock('@renderer/api/client', () => ({
  api: { get: mocks.get, post: mocks.post },
  setUnauthorizedHandler: (handler: () => void) => {
    mocks.unauthorizedHandler = handler
  }
}))

const { useAuthStore } = await import('./auth')

const USER = { id: 'kc_user_1', username: 'alice', created_at: '2026-09-11T00:00:00' }

/** /health 与 /auth/me 按路径分别应答 */
function mockBackend(mode: 'single' | 'multiuser', me?: Promise<unknown>): void {
  mocks.get.mockImplementation((url: string) => {
    if (url === '/health') return Promise.resolve({ app: 'kate-cortex', mode })
    if (url === '/auth/me') return me ?? Promise.reject(new Error('401'))
    return Promise.reject(new Error(`unexpected get: ${url}`))
  })
}

describe('auth store（Web 形态）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({ user: null, ready: false })
  })

  it('单用户后端（如 Vercel 试用）：免登录直通占位用户', async () => {
    mockBackend('single')
    await useAuthStore.getState().ensureLoaded()
    expect(useAuthStore.getState().user).toEqual({
      id: 'local',
      username: 'local',
      created_at: ''
    })
    expect(useAuthStore.getState().ready).toBe(true)
    expect(mocks.get).not.toHaveBeenCalledWith('/auth/me')
  })

  it('多用户后端：经 /auth/me 恢复会话', async () => {
    mockBackend('multiuser', Promise.resolve(USER))
    await useAuthStore.getState().ensureLoaded()
    expect(useAuthStore.getState().user).toEqual(USER)
    expect(useAuthStore.getState().ready).toBe(true)
  })

  it('多用户后端会话失效：置空用户并进入就绪（AuthGate 渲染登录页）', async () => {
    mockBackend('multiuser', Promise.reject(new Error('401')))
    await useAuthStore.getState().ensureLoaded()
    expect(useAuthStore.getState().user).toBeNull()
    expect(useAuthStore.getState().ready).toBe(true)
  })

  it('登录成功写入用户', async () => {
    mocks.post.mockResolvedValueOnce(USER)
    await useAuthStore.getState().login('alice', 'pass123')
    expect(mocks.post).toHaveBeenCalledWith('/auth/login', {
      username: 'alice',
      password: 'pass123'
    })
    expect(useAuthStore.getState().user).toEqual(USER)
  })

  it('注册携带邀请码（空串不下发）', async () => {
    mocks.post.mockResolvedValueOnce(USER)
    await useAuthStore.getState().register('bob', 'pass123', ' letmein ')
    expect(mocks.post).toHaveBeenCalledWith('/auth/register', {
      username: 'bob',
      password: 'pass123',
      invite_code: 'letmein'
    })
  })

  it('任何 API 401 → 清空登录态（AuthGate 切到登录页）', async () => {
    mocks.post.mockResolvedValueOnce(USER)
    await useAuthStore.getState().login('alice', 'pass123')
    expect(useAuthStore.getState().user).not.toBeNull()

    mocks.unauthorizedHandler?.()
    expect(useAuthStore.getState().user).toBeNull()
  })

  it('登出后置空用户', async () => {
    mocks.post.mockResolvedValueOnce(USER)
    await useAuthStore.getState().login('alice', 'pass123')
    mocks.post.mockResolvedValueOnce(undefined)
    await useAuthStore.getState().logout()
    expect(useAuthStore.getState().user).toBeNull()
  })
})
