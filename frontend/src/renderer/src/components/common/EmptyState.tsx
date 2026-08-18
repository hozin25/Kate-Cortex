import type { ReactNode } from 'react'
import { motion } from 'motion/react'
import { cn } from '@renderer/lib/utils'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  hint?: string
  action?: ReactNode
  className?: string
}

export function EmptyState({
  icon,
  title,
  hint,
  action,
  className
}: EmptyStateProps): React.JSX.Element {
  return (
    <div
      className={cn('flex flex-col items-center justify-center gap-3 py-16 text-center', className)}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: 'spring', stiffness: 160, damping: 18 }}
        className="grid size-14 place-items-center rounded-2xl border border-white/10 bg-white/[0.04] text-zinc-400"
      >
        {icon}
      </motion.div>
      <div className="font-display text-sm text-zinc-300">{title}</div>
      {hint && <div className="max-w-xs text-xs leading-5 text-zinc-500">{hint}</div>}
      {action}
    </div>
  )
}
