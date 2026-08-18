import { AnimatePresence, motion } from 'motion/react'
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'
import { useToastStore } from '@renderer/stores/toast'

const KIND_STYLES = {
  error: 'border-rose-400/25 bg-rose-500/12 text-rose-100',
  success: 'border-emerald-400/25 bg-emerald-500/12 text-emerald-100',
  info: 'border-sky-400/25 bg-sky-500/12 text-sky-100'
} as const

const KIND_ICONS = {
  error: AlertCircle,
  success: CheckCircle2,
  info: Info
} as const

export function ToastHost(): React.JSX.Element {
  const toasts = useToastStore((s) => s.toasts)
  const dismiss = useToastStore((s) => s.dismiss)

  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-50 flex flex-col items-center gap-2 px-4">
      <AnimatePresence>
        {toasts.map((t) => {
          const Icon = KIND_ICONS[t.kind]
          return (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: -12, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.97 }}
              transition={{ duration: 0.22, ease: [0.21, 1, 0.35, 1] }}
              className={`pointer-events-auto flex max-w-lg items-center gap-2.5 rounded-xl border px-4 py-2.5 text-[13px] shadow-lg backdrop-blur-xl ${KIND_STYLES[t.kind]}`}
            >
              <Icon className="size-4 shrink-0" />
              <span className="leading-5">{t.message}</span>
              <button
                onClick={() => dismiss(t.id)}
                className="ml-1 rounded-md p-0.5 opacity-60 transition hover:opacity-100"
                aria-label="关闭"
              >
                <X className="size-3.5" />
              </button>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
