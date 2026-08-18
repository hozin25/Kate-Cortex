import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '@renderer/lib/utils'

interface GlassPanelProps extends HTMLAttributes<HTMLDivElement> {
  deep?: boolean
  children: ReactNode
}

export function GlassPanel({
  deep,
  className,
  children,
  ...rest
}: GlassPanelProps): React.JSX.Element {
  return (
    <div className={cn(deep ? 'glass-deep' : 'glass', 'rounded-2xl', className)} {...rest}>
      {children}
    </div>
  )
}

interface GradientTextProps {
  children: ReactNode
  className?: string
}

export function GradientText({ children, className }: GradientTextProps): React.JSX.Element {
  return <span className={cn('text-gradient font-display', className)}>{children}</span>
}
