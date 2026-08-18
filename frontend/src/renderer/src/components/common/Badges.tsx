import { Loader2 } from 'lucide-react'
import { cn } from '@renderer/lib/utils'
import { TYPE_LABELS, TYPE_STYLES } from '@renderer/lib/utils'

interface SpinnerProps {
  className?: string
}

export function Spinner({ className }: SpinnerProps): React.JSX.Element {
  return <Loader2 className={cn('size-4 animate-spin', className)} />
}

interface TypeBadgeProps {
  type: string
  className?: string
}

export function TypeBadge({ type, className }: TypeBadgeProps): React.JSX.Element {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[11px] leading-none',
        TYPE_STYLES[type] ?? 'bg-white/10 text-zinc-300 border-white/15',
        className
      )}
    >
      {TYPE_LABELS[type] ?? type}
    </span>
  )
}
