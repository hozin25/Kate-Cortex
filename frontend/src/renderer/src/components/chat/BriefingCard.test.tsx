import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BriefingCard } from '@renderer/components/chat/BriefingCard'
import type { Briefing } from '@renderer/types'

const api = vi.hoisted(() => ({
  get: vi.fn()
}))

vi.mock('@renderer/api/client', () => ({ api }))

function briefing(): Briefing {
  return {
    date: new Date().toISOString().slice(0, 10),
    greeting: '早上好，主人。',
    items: [
      { kind: 'due', text: '今天 10:00 有复诊', entry_id: 'kc_1' },
      { kind: 'tip', text: '昨晚睡得晚，今天早点休息', entry_id: null }
    ],
    cached: false
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('BriefingCard', () => {
  it('渲染问候与分条目（含 kind 标签）', async () => {
    api.get.mockResolvedValueOnce(briefing())

    render(<BriefingCard />)

    expect(await screen.findByText('早上好，主人。')).toBeInTheDocument()
    expect(screen.getByText('今天 10:00 有复诊')).toBeInTheDocument()
    expect(screen.getByText('昨晚睡得晚，今天早点休息')).toBeInTheDocument()
    expect(screen.getByText('到期')).toBeInTheDocument()
    expect(screen.getByText('建议')).toBeInTheDocument()
  })

  it('关闭后当日不再拉取（localStorage 记住日期）', async () => {
    api.get.mockResolvedValueOnce(briefing())

    render(<BriefingCard />)
    await waitFor(() => expect(screen.getByText('早上好，主人。')).toBeInTheDocument())

    await userEvent.click(screen.getByLabelText('关闭今日简报'))

    expect(screen.queryByText('早上好，主人。')).not.toBeInTheDocument()
    expect(localStorage.getItem('kate_briefing_dismissed')).toBe(
      new Date().toISOString().slice(0, 10)
    )

    // 再次挂载：已关闭 → 不发请求
    render(<BriefingCard />)
    expect(api.get).toHaveBeenCalledTimes(1)
  })

  it('接口失败时静默隐藏，不渲染卡片', async () => {
    api.get.mockRejectedValueOnce(new Error('未配置 glm 的 API key'))

    const { container } = render(<BriefingCard />)

    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1))
    expect(container).toBeEmptyDOMElement()
  })
})
