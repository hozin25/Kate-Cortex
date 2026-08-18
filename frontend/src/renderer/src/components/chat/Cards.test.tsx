import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { SavedCard, SuggestCard } from '@renderer/components/chat/Cards'
import type { SavedPayload, SuggestPayload } from '@renderer/types'

const saved: SavedPayload = {
  entry_id: 'kc_20260818_001',
  slug: 'sqlite-dan-wen-jian-shu-ju-ku',
  title: 'SQLite 是单文件数据库',
  type: 'decision',
  tags: ['sqlite', '选型']
}

const suggest: SuggestPayload = {
  title: '连接池调优方案',
  type: 'howto',
  tags: ['sqlite', '性能'],
  preview: 'max_size 设为 20，pool_pre_ping 开启可避免断连后取到失效连接。'
}

describe('SavedCard', () => {
  it('渲染标题、类型徽标与标签，并提供跳详情链接', () => {
    render(
      <MemoryRouter>
        <SavedCard saved={saved} />
      </MemoryRouter>
    )
    expect(screen.getByText('SQLite 是单文件数据库')).toBeInTheDocument()
    expect(screen.getByText('决策')).toBeInTheDocument()
    expect(screen.getByText('#sqlite')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /查看/ })).toHaveAttribute(
      'href',
      `/entries/${saved.entry_id}`
    )
  })
})

describe('SuggestCard 确认流', () => {
  it('点击「存入知识库」后 POST /api/entries 并转为已保存态', async () => {
    const postMock = vi.fn().mockResolvedValue({ id: 'kc_20260818_002' })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        expect(String(url)).toMatch(/\/api\/entries$/)
        expect(init?.method).toBe('POST')
        const body = JSON.parse(String(init?.body))
        expect(body).toMatchObject({ title: suggest.title, type: suggest.type, source: 'chat' })
        return Promise.resolve({ ok: true, status: 201, json: postMock })
      })
    )
    const onDismiss = vi.fn()

    render(
      <MemoryRouter>
        <SuggestCard suggest={suggest} conversationId="kc_conv_abc" onDismiss={onDismiss} />
      </MemoryRouter>
    )
    expect(screen.getByText('连接池调优方案')).toBeInTheDocument()

    await userEvent.setup().click(screen.getByRole('button', { name: '存入知识库' }))

    await waitFor(() => {
      expect(screen.getByText('已存入知识库')).toBeInTheDocument()
    })
    expect(postMock).toHaveBeenCalledTimes(1)
    expect(onDismiss).not.toHaveBeenCalled()
    expect(screen.getByRole('link', { name: /查看/ })).toHaveAttribute(
      'href',
      '/entries/kc_20260818_002'
    )
    vi.unstubAllGlobals()
  })

  it('点击「忽略」不发送请求，直接移除', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const onDismiss = vi.fn()
    render(
      <MemoryRouter>
        <SuggestCard suggest={suggest} conversationId="kc_conv_abc" onDismiss={onDismiss} />
      </MemoryRouter>
    )
    await userEvent.setup().click(screen.getByRole('button', { name: '忽略' }))
    expect(onDismiss).toHaveBeenCalledTimes(1)
    expect(fetchMock).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
