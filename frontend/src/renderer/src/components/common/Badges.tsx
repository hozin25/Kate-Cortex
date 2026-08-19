import { Loader2 } from 'lucide-react'
import { cn } from '@renderer/lib/utils'

interface SpinnerProps {
  className?: string
}

export function Spinner({ className }: SpinnerProps): React.JSX.Element {
  return <Loader2 className={cn('size-4 animate-spin', className)} />
}
