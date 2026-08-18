import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { StreamingBubble } from '@renderer/components/chat/MessageBubble'

vi.mock('shiki', () => ({
  createHighlighter: vi.fn().mockRejectedValue(new Error('shiki disabled in test'))
}))

describe('StreamingBubble 流式文本追加', () => {
  it('空文本时仅显示打字光标占位', () => {
    render(<StreamingBubble text="" />)
    expect(screen.getByText('正在思考…')).toBeInTheDocument()
    expect(document.querySelector('.animate-cursor-blink')).not.toBeNull()
  })

  it('增量文本随 props 追加渲染', () => {
    const { rerender } = render(<StreamingBubble text="SQLite 是" />)
    expect(screen.getByText(/SQLite 是/)).toBeInTheDocument()

    rerender(<StreamingBubble text="SQLite 是嵌入式的单文件数据库" />)
    expect(screen.getByText(/嵌入式的单文件数据库/)).toBeInTheDocument()
  })

  it('markdown 片段按富文本渲染', () => {
    render(
      <MemoryRouter>
        <StreamingBubble text={'**结论**：选 SQLite\n\n- 零运维\n- 单文件'} />
      </MemoryRouter>
    )
    expect(screen.getByText('结论').tagName).toBe('STRONG')
    expect(screen.getByText('零运维').tagName).toBe('LI')
  })
})
