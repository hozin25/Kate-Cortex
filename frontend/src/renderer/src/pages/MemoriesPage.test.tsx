import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoriesPage } from '@renderer/pages/MemoriesPage'
import type { EntrySummary } from '@renderer/types'

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn()
}))

vi.mock('@renderer/api/client', () => ({ api }))

function memory(partial: Partial<EntrySummary> = {}): EntrySummary {
  return {
    id: 'kc_20260906_001',
    slug: 'gan-mao',
    title: '感冒了',
    collections: ['记忆'],
    source: 'chat',
    language: null,
    conversation_id: 'kc_conv_x',
    keywords: ['感冒', '健康'],
    importance: 4,
    created_at: '2026-09-06T10:00:00',
    updated_at: '2026-09-06T10:00:00',
    ...partial
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('MemoriesPage', () => {
  it('按重要度排序列出记忆并展示关键词', async () => {
    api.get.mockResolvedValueOnce({
      items: [memory({ id: 'low', title: '低重要度', importance: 2, keywords: ['出行'] }), memory()]
    })

    render(<MemoriesPage />)

    await waitFor(() => expect(screen.getByText('感冒了')).toBeInTheDocument())
    const titles = document.querySelectorAll('.text-sm.text-zinc-100')
    expect(titles[0].textContent).toBe('感冒了')
    expect(titles[1].textContent).toBe('低重要度')
    expect(screen.getByText('感冒')).toBeInTheDocument()
    expect(screen.getByText('健康')).toBeInTheDocument()
  })

  it('空列表显示引导空状态', async () => {
    api.get.mockResolvedValueOnce({ items: [], total: 0 })

    render(<MemoriesPage />)

    await waitFor(() => expect(screen.getByText('还没有记忆')).toBeInTheDocument())
  })

  it('搜索按标题与关键词过滤', async () => {
    api.get.mockResolvedValueOnce({
      items: [memory(), memory({ id: 'x2', title: '出行计划', keywords: ['出行'] })]
    })

    render(<MemoriesPage />)
    await waitFor(() => expect(screen.getByText('出行计划')).toBeInTheDocument())

    await userEvent.type(screen.getByPlaceholderText('搜索标题 / 关键词'), '感冒')

    expect(screen.getByText('感冒了')).toBeInTheDocument()
    expect(screen.queryByText('出行计划')).not.toBeInTheDocument()
  })

  it('编辑：展开详情后可保存修改', async () => {
    api.get.mockResolvedValueOnce({ items: [memory()] })
    api.get.mockResolvedValueOnce({
      id: 'kc_20260906_001',
      slug: 'gan-mao',
      title: '感冒了',
      collections: ['记忆'],
      source: 'chat',
      language: null,
      conversation_id: 'kc_conv_x',
      file_path: 'x.md',
      keywords: ['感冒', '健康'],
      importance: 4,
      content: '8月30日感冒，注意保暖',
      created_at: '2026-09-06T10:00:00',
      updated_at: '2026-09-06T10:00:00'
    })
    api.put.mockResolvedValueOnce({})
    api.get.mockResolvedValueOnce({ items: [memory({ title: '感冒康复了', importance: 2 })] })

    render(<MemoriesPage />)
    await waitFor(() => expect(screen.getByText('感冒了')).toBeInTheDocument())

    await userEvent.click(screen.getByLabelText('编辑记忆'))
    const titleInput = await screen.findByDisplayValue('感冒了')
    await userEvent.clear(titleInput)
    await userEvent.type(titleInput, '感冒康复了')
    await userEvent.click(screen.getByText('保存'))

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith(
        '/entries/kc_20260906_001',
        expect.objectContaining({ title: '感冒康复了', importance: 4 })
      )
    )
    await waitFor(() => expect(screen.getByText('感冒康复了')).toBeInTheDocument())
  })

  it('删除：确认后调用删除接口', async () => {
    api.get.mockResolvedValueOnce({ items: [memory()] })
    api.delete.mockResolvedValueOnce(undefined)
    api.get.mockResolvedValueOnce({ items: [], total: 0 })
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<MemoriesPage />)
    await waitFor(() => expect(screen.getByText('感冒了')).toBeInTheDocument())

    await userEvent.click(screen.getByLabelText('删除记忆'))

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/entries/kc_20260906_001'))
  })
})
