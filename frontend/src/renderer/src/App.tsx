import { useEffect } from 'react'
import {
  NavLink,
  Route,
  HashRouter,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams
} from 'react-router-dom'
import { Brain, Library, MessagesSquare, Settings } from 'lucide-react'
import { ChatPage } from '@renderer/pages/ChatPage'
import { LibraryPage } from '@renderer/pages/LibraryPage'
import { MemoriesPage } from '@renderer/pages/MemoriesPage'
import { TrashPage } from '@renderer/pages/TrashPage'
import { EntryDetailPage } from '@renderer/pages/EntryDetailPage'
import { EntryEditPage } from '@renderer/pages/EntryEditPage'
import { SettingsPage } from '@renderer/pages/SettingsPage'
import { SessionSidebar } from '@renderer/components/chat/SessionSidebar'
import { GradientText } from '@renderer/components/common/Glass'
import { ToastHost } from '@renderer/components/common/ToastHost'
import { useSettingsStore } from '@renderer/stores/settings'
import { useChatStore } from '@renderer/stores/chat'
import { cn } from '@renderer/lib/utils'

const NAV_ITEMS = [
  { to: '/', icon: MessagesSquare, label: '对话' },
  { to: '/library', icon: Library, label: '知识库' },
  { to: '/memories', icon: Brain, label: '记忆' },
  { to: '/settings', icon: Settings, label: '设置' }
]

export function App(): React.JSX.Element {
  return (
    <HashRouter>
      <div className="space-bg" />
      <div className="flex h-full">
        <Sidebar />
        <main className="min-w-0 flex-1">
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/memories" element={<MemoriesPage />} />
            <Route path="/trash" element={<TrashPage />} />
            <Route path="/entries/new" element={<EntryEditPage />} />
            <Route path="/entries/:id" element={<EntryDetailPage />} />
            <Route path="/entries/:id/edit" element={<EntryEditPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
      <ToastHost />
      <GlobalShortcuts />
      <SessionDeepLink />
    </HashRouter>
  )
}

function Sidebar(): React.JSX.Element {
  const location = useLocation()
  const loadSettings = useSettingsStore((s) => s.load)

  useEffect(() => {
    void loadSettings().catch(() => undefined)
  }, [loadSettings])

  const onChat = location.pathname === '/'
  return (
    <aside className="glass-deep flex w-64 shrink-0 flex-col border-r border-white/[0.06] bg-ink-950/60">
      <div className="px-5 pb-4 pt-5">
        <div className="font-display text-lg tracking-wide">
          <GradientText>Kate</GradientText>
          <span className="ml-2 text-[10px] font-normal uppercase tracking-[0.2em] text-zinc-600">
            cortex
          </span>
        </div>
      </div>
      <nav className="space-y-0.5 px-3">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] transition',
                isActive
                  ? 'bg-aurora-indigo/15 text-zinc-100 shadow-[inset_0_0_0_1px] shadow-aurora-indigo/25'
                  : 'text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-200'
              )
            }
          >
            <Icon className="size-4" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="mx-3 my-3 border-t border-white/[0.06]" />
      {onChat ? <SessionSidebar /> : <div className="flex-1" />}
      <div className="px-5 pb-4 pt-2 text-[10px] text-zinc-700">本地优先 · 数据在你手里</div>
    </aside>
  )
}

/** 详情页「来自对话」跳回：/?session=<id> */
function SessionDeepLink(): null {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const selectSession = useChatStore((s) => s.selectSession)
  const session = params.get('session')

  useEffect(() => {
    if (!session) return
    void selectSession(session).catch(() => undefined)
    navigate('/', { replace: true })
  }, [session, selectSession, navigate])

  return null
}

function GlobalShortcuts(): null {
  const navigate = useNavigate()
  const createSession = useChatStore((s) => s.createSession)
  const settings = useSettingsStore((s) => s.settings)

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.ctrlKey && e.key.toLowerCase() === 'n') {
        e.preventDefault()
        void createSession(settings?.default_provider ?? 'deepseek').catch(() => undefined)
        navigate('/')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [createSession, navigate, settings?.default_provider])

  return null
}
