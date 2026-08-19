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
  collections: ['选型复盘']
}

const suggest: SuggestPayload = {
  title: '连接池调优方案',
  collections: ['编程'],
  preview: 'max_size 设为 20，pool_pre_ping 开启可避免断连后取到失效连接。'
}

describe('SavedCard', () => {
  it('渲染标题与合集，并提供跳详情链接', () => {
    render(
      <MemoryRouter>
        <SavedCard saved={saved} />
      </MemoryRouter>
    )
    expect(screen.getByText('SQLite 是单文件数据库')).toBeInTheDocument()
    expect(screen.getByText('选型复盘')).toBeInTheDocument()
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
        if (String(url).match(/\/api\/collections$/)) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () =>
              Promise.resolve([
                { name: '编程', count: 1 },
                { name: '情感', count: 0 }
              ])
          })
        }
        expect(String(url)).toMatch(/\/api\/entries$/)
        expect(init?.method).toBe('POST')
        const body = JSON.parse(String(init?.body))
        expect(body).toMatchObject({
          title: suggest.title,
          collections: ['编程'],
          source: 'chat'
        })
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

  it('可增删建议合集后再保存', async () => {
    const postMock = vi.fn().mockResolvedValue({ id: 'kc_20260818_003' })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (String(url).match(/\/api\/collections$/)) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () =>
              Promise.resolve([
                { name: '编程', count: 1 },
                { name: '情感', count: 0 }
              ])
          })
        }
        const body = JSON.parse(String(init?.body))
        expect(body.collections).toEqual(['编程', '情感'])
        return Promise.resolve({ ok: true, status: 201, json: postMock })
      })
    )
    const onDismiss = vi.fn()

    render(
      <MemoryRouter>
        <SuggestCard suggest={suggest} conversationId="kc_conv_abc" onDismiss={onDismiss} />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /情感/ })).toBeInTheDocument()
    })
    await userEvent.setup().click(screen.getByRole('button', { name: /情感/ }))
    await userEvent.setup().click(screen.getByRole('button', { name: '存入知识库' }))

    await waitFor(() => {
      expect(screen.getByText('已存入知识库')).toBeInTheDocument()
    })
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
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/entries$/),
      expect.anything()
    )
    vi.unstubAllGlobals()
  })
})
