import { useEffect, useState } from 'react'
import { AlarmClock, BellRing, Lightbulb, X } from 'lucide-react'
import { api } from '@renderer/api/client'
import type { Briefing, BriefingItem } from '@renderer/types'

const DISMISS_KEY = 'kate_briefing_dismissed'

const KIND_META: Record<BriefingItem['kind'], { icon: typeof BellRing; label: string }> = {
  due: { icon: AlarmClock, label: '到期' },
  followup: { icon: BellRing, label: '跟进' },
  tip: { icon: Lightbulb, label: '建议' }
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

/**
 * 管家每日简报（BRIEFING_PLAN.md §3）：对话页顶部极光描边卡，当日关闭后
 * 不再拉取；拉取成功时对到期项发一条系统通知（仅在权限已授予时）。
 */
export function BriefingCard(): React.JSX.Element | null {
  const [briefing, setBriefing] = useState<Briefing | null>(null)

  useEffect(() => {
    if (localStorage.getItem(DISMISS_KEY) === today()) return
    let cancelled = false
    api
      .get<Briefing>('/briefing')
      .then((result) => {
        if (cancelled) return
        setBriefing(result)
        notifyDueItems(result)
      })
      .catch(() => undefined) // 静默降级：简报失败不影响对话
    return () => {
      cancelled = true
    }
  }, [])

  const dismiss = (): void => {
    localStorage.setItem(DISMISS_KEY, today())
    setBriefing(null)
  }

  if (!briefing) return null
  const dateLabel = `${Number(briefing.date.slice(5, 7))}月${Number(briefing.date.slice(8, 10))}日`

  return (
    <div className="relative rounded-2xl border border-aurora-cyan/25 bg-gradient-to-br from-aurora-indigo/15 via-transparent to-aurora-cyan/10 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-display text-[11px] uppercase tracking-[0.25em] text-aurora-cyan">
            {dateLabel} · 管家简报
          </div>
          <p className="mt-1 text-sm text-zinc-100">{briefing.greeting}</p>
        </div>
        <button
          onClick={dismiss}
          className="grid size-6 shrink-0 place-items-center rounded-lg text-zinc-500 transition hover:bg-white/[0.06] hover:text-zinc-200"
          aria-label="关闭今日简报"
        >
          <X className="size-3.5" />
        </button>
      </div>
      {briefing.items.length > 0 && (
        <ul className="mt-2.5 space-y-1.5">
          {briefing.items.map((item, index) => {
            const meta = KIND_META[item.kind] ?? KIND_META.followup
            const Icon = meta.icon
            return (
              <li
                key={index}
                className="flex items-start gap-2 text-[13px] leading-5 text-zinc-300"
              >
                <Icon className="mt-0.5 size-3.5 shrink-0 text-aurora-cyan/80" />
                <span className="min-w-0">
                  <span className="mr-1.5 text-[10px] text-zinc-500">{meta.label}</span>
                  {item.text}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function notifyDueItems(briefing: Briefing): void {
  const due = briefing.items.filter((item) => item.kind === 'due')
  if (due.length === 0) return
  try {
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return
    new Notification('Kate · 今日提醒', { body: due.map((item) => item.text).join('\n') })
  } catch {
    // 通知不可用（无头环境/权限受限）静默跳过
  }
}
