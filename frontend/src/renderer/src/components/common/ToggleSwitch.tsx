import { cn } from '@renderer/lib/utils'

interface ToggleSwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
}

export function ToggleSwitch({ checked, onChange }: ToggleSwitchProps): React.JSX.Element {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={cn(
        'relative h-6 w-11 shrink-0 rounded-full border transition',
        checked ? 'border-aurora-cyan/40 bg-aurora-cyan/25' : 'border-white/10 bg-white/[0.06]'
      )}
      role="switch"
      aria-checked={checked}
    >
      <span
        className={cn(
          'absolute top-0.5 size-4.5 rounded-full transition-all',
          checked
            ? 'left-[22px] bg-aurora-cyan shadow-[0_0_8px] shadow-aurora-cyan'
            : 'left-0.5 bg-zinc-400'
        )}
      />
    </button>
  )
}
