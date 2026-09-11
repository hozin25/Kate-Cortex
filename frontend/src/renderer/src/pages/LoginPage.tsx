import { useState } from 'react'
import { GradientText } from '@renderer/components/common/Glass'
import { Spinner } from '@renderer/components/common/Badges'
import { useAuthStore } from '@renderer/stores/auth'
import { cn } from '@renderer/lib/utils'

/** 多用户版登录/注册页（仅 Web 形态；Electron 单用户不经过这里） */
export function LoginPage(): React.JSX.Element {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const login = useAuthStore((s) => s.login)
  const register = useAuthStore((s) => s.register)

  const submit = (e: React.FormEvent): void => {
    e.preventDefault()
    if (busy) return
    setError(null)
    setBusy(true)
    const action =
      mode === 'login'
        ? login(username.trim(), password)
        : register(username.trim(), password, inviteCode)
    void action
      .catch((err) => setError(err instanceof Error ? err.message : '请求失败'))
      .finally(() => setBusy(false))
  }

  return (
    <div className="flex h-full items-center justify-center px-4">
      <form
        onSubmit={submit}
        className="glass-deep w-full max-w-sm rounded-2xl border border-white/[0.07] bg-ink-950/70 p-6"
      >
        <div className="text-center">
          <div className="font-display text-xl tracking-wide">
            <GradientText>Kate</GradientText>
            <span className="ml-2 text-[10px] font-normal uppercase tracking-[0.2em] text-zinc-600">
              cortex
            </span>
          </div>
          <p className="mt-2 text-xs text-zinc-500">
            {mode === 'login' ? '登录你的知识库' : '创建你的知识库账号'}
          </p>
        </div>

        <div className="mt-5 space-y-3">
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="用户名"
            autoComplete="username"
            className="glass-deep w-full rounded-xl px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="密码"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            className="glass-deep w-full rounded-xl px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
          />
          {mode === 'register' && (
            <input
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              placeholder="邀请码（如需要）"
              autoComplete="off"
              className="glass-deep w-full rounded-xl px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
            />
          )}
        </div>

        {error && <p className="mt-3 text-xs text-rose-300/90">✕ {error}</p>}

        <button
          type="submit"
          disabled={busy || !username.trim() || !password}
          className="mt-5 flex w-full items-center justify-center gap-1.5 rounded-xl border border-aurora-indigo/30 bg-aurora-indigo/15 px-3 py-2.5 text-sm text-zinc-100 transition hover:brightness-125 disabled:opacity-40"
        >
          {busy && <Spinner className="size-3.5" />}
          {mode === 'login' ? '登录' : '注册并进入'}
        </button>

        <button
          type="button"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login')
            setError(null)
          }}
          className={cn(
            'mt-3 w-full text-center text-xs text-zinc-500 transition hover:text-zinc-300'
          )}
        >
          {mode === 'login' ? '没有账号？注册一个' : '已有账号？去登录'}
        </button>
      </form>
    </div>
  )
}
