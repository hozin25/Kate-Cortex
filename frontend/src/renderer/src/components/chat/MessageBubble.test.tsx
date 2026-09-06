import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { MessageBubble, StreamingBubble } from '@renderer/components/chat/MessageBubble'
import type { ChatMessage } from '@renderer/types'

vi.mock('shiki', () => ({
  createHighlighter: vi.fn().mockRejectedValue(new Error('shiki disabled in test'))
}))

function userMessage(content: string): ChatMessage {
  return {
    id: 'm1',
    conversation_id: 'c1',
    role: 'user',
    content,
    tool_calls: null,
    knowledge_refs: null,
    created_at: '2026-09-01T00:00:00'
  }
}

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

describe('MessageBubble 用户消息图片', () => {
  it('含附件引用的消息渲染为图片', () => {
    render(
      <MemoryRouter>
        <MessageBubble
          message={userMessage('这是什么报错\n\n![图片](attachments/2026/09/a.png)')}
        />
      </MemoryRouter>
    )
    const img = screen.getByAltText('图片')
    expect(img.getAttribute('src')).toBe('http://127.0.0.1:1738/api/attachments/2026/09/a.png')
  })

  it('纯文本消息不套 markdown 渲染', () => {
    render(
      <MemoryRouter>
        <MessageBubble message={userMessage('普通文本\n多行')} />
      </MemoryRouter>
    )
    const p = document.querySelector('p.whitespace-pre-wrap')
    expect(p).not.toBeNull()
    expect(p?.textContent).toContain('普通文本')
    expect(p?.textContent).toContain('多行')
  })
})
