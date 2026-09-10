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
import { Brain, Library, MessagesSquare, Settings, X } from 'lucide-react'
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
import { useLibraryStore } from '@renderer/stores/library'
import { useUiStore } from '@renderer/stores/ui'
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
        <div className="flex min-w-0 flex-1 flex-col">
          {/* min-h-0：纵向 flex 里允许 main 收敛到一屏内，页面自身的滚动容器才能生效 */}
          <main className="min-h-0 min-w-0 flex-1">
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
          <MobileTabNav />
        </div>
      </div>
      <SessionsDrawer />
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
    <aside className="glass-deep hidden w-64 shrink-0 flex-col border-r border-white/[0.06] bg-ink-950/60 md:flex">
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

/** 窄屏底部标签栏（≥md 由左侧栏接管） */
function MobileTabNav(): React.JSX.Element {
  return (
    <nav className="glass-deep flex shrink-0 items-stretch justify-around border-t border-white/[0.06] bg-ink-950/80 pb-[env(safe-area-inset-bottom)] md:hidden">
      {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            cn(
              'flex flex-1 flex-col items-center gap-0.5 rounded-xl py-2 text-[10px] transition',
              isActive ? 'text-aurora-cyan' : 'text-zinc-500 hover:text-zinc-300'
            )
          }
        >
          <Icon className="size-5" />
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

/** 窄屏会话抽屉：从对话页头部按钮唤出，包含新会话按钮与会话列表 */
function SessionsDrawer(): React.JSX.Element {
  const open = useUiStore((s) => s.sessionsOpen)
  const setOpen = useUiStore((s) => s.setSessionsOpen)
  const location = useLocation()

  // 路由变化时收起，避免抽屉盖在新页面上
  useEffect(() => {
    setOpen(false)
  }, [location.pathname, setOpen])

  if (!open) return <></>
  return (
    <div className="fixed inset-0 z-50 md:hidden">
      <div
        className="animate-fade-in absolute inset-0 bg-black/55 backdrop-blur-sm"
        onClick={() => setOpen(false)}
      />
      <div className="glass-deep animate-drawer-in absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-white/[0.08] bg-ink-950/95">
        <div className="flex items-center justify-between px-5 pb-3 pt-5">
          <div className="font-display text-lg tracking-wide">
            <GradientText>Kate</GradientText>
            <span className="ml-2 text-[10px] font-normal uppercase tracking-[0.2em] text-zinc-600">
              cortex
            </span>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="grid size-8 place-items-center rounded-xl text-zinc-500 transition hover:bg-white/[0.06] hover:text-zinc-200"
            aria-label="关闭"
          >
            <X className="size-4" />
          </button>
        </div>
        <SessionSidebar />
        <div className="px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-2 text-[10px] text-zinc-700">
          本地优先 · 数据在你手里
        </div>
      </div>
    </div>
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
  const requestFocusSearch = useLibraryStore((s) => s.requestFocusSearch)

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.ctrlKey && e.key.toLowerCase() === 'n') {
        e.preventDefault()
        void createSession(settings?.default_provider ?? 'deepseek').catch(() => undefined)
        navigate('/')
      } else if (e.ctrlKey && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        requestFocusSearch()
        navigate('/library')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [createSession, navigate, settings?.default_provider, requestFocusSearch])

  return null
}
