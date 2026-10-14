import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CapturePage } from '@renderer/pages/CapturePage'

const api = vi.hoisted(() => ({
  post: vi.fn()
}))

vi.mock('@renderer/api/client', () => ({ api }))

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(window, 'close').mockImplementation(() => undefined)
})

describe('CapturePage', () => {
  it('Ctrl+Enter 保存：POST /capture，成功后清空并关窗', async () => {
    api.post.mockResolvedValueOnce({
      entry_id: 'kc_1',
      slug: 'x',
      title: '灵感一则',
      enriched: true
    })
    const user = userEvent.setup()

    render(<CapturePage />)
    const textarea = screen.getByRole('textbox')
    await user.type(textarea, '灵感一则')

    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true })

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/capture', { text: '灵感一则' }))
    await waitFor(() => expect(window.close).toHaveBeenCalledTimes(1))
  })

  it('Esc 关闭窗口（不提交）', async () => {
    const user = userEvent.setup()

    render(<CapturePage />)
    const textarea = screen.getByRole('textbox')
    await user.type(textarea, '随便写点')

    fireEvent.keyDown(textarea, { key: 'Escape' })

    expect(window.close).toHaveBeenCalledTimes(1)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('空内容不提交', async () => {
    render(<CapturePage />)

    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter', ctrlKey: true })

    expect(api.post).not.toHaveBeenCalled()
    expect(window.close).not.toHaveBeenCalled()
  })

  it('保存失败：报错并保留内容可重试', async () => {
    api.post.mockRejectedValueOnce(new Error('网络错误'))
    const user = userEvent.setup()

    render(<CapturePage />)
    const textarea = screen.getByRole('textbox')
    await user.type(textarea, '不能丢的内容')
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true })

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
    expect(window.close).not.toHaveBeenCalled()
    expect(screen.getByRole('textbox')).toHaveValue('不能丢的内容')
  })
})
