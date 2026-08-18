import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

export function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

export const TYPE_LABELS: Record<string, string> = {
  note: '笔记',
  clip: '剪藏',
  decision: '决策',
  howto: '方法'
}

export const TYPE_STYLES: Record<string, string> = {
  note: 'bg-sky-400/15 text-sky-300 border-sky-400/25',
  clip: 'bg-amber-400/15 text-amber-300 border-amber-400/25',
  decision: 'bg-rose-400/15 text-rose-300 border-rose-400/25',
  howto: 'bg-emerald-400/15 text-emerald-300 border-emerald-400/25'
}
