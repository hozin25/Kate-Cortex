import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

describe('MessageBubble 对话管理操作', () => {
  function assistantMessage(id = 'a1'): ChatMessage {
    return {
      ...userMessage('回答'),
      id,
      role: 'assistant',
      knowledge_refs: null
    }
  }

  it('用户消息悬停提供 复制/编辑/删除', () => {
    render(
      <MemoryRouter>
        <MessageBubble message={userMessage('你好')} onDelete={() => undefined} />
      </MemoryRouter>
    )
    expect(screen.getByLabelText('复制')).toBeInTheDocument()
    expect(screen.getByLabelText('编辑')).toBeInTheDocument()
    expect(screen.getByLabelText('删除')).toBeInTheDocument()
  })

  it('编辑进入内联编辑器，重发回调携带新文本（剥离图片引用）', async () => {
    const onEdit = vi.fn()
    render(
      <MemoryRouter>
        <MessageBubble
          message={userMessage('这是什么\n\n![图片](attachments/2026/09/a.png)')}
          onEdit={onEdit}
        />
      </MemoryRouter>
    )
    await userEvent.click(screen.getByLabelText('编辑'))
    const textarea = screen.getByRole('textbox')
    expect(textarea).toHaveValue('这是什么') // 图片引用不进编辑框
    await userEvent.clear(textarea)
    await userEvent.type(textarea, '改后的问题')
    await userEvent.click(screen.getByText('重发'))
    expect(onEdit).toHaveBeenCalledWith('改后的问题')
  })

  it('最后一条 AI 回复提供重新生成，非最后一条不提供', () => {
    const { rerender } = render(
      <MemoryRouter>
        <MessageBubble message={assistantMessage()} isLast onRegenerate={() => undefined} />
      </MemoryRouter>
    )
    expect(screen.getByLabelText('重新生成')).toBeInTheDocument()

    rerender(
      <MemoryRouter>
        <MessageBubble message={assistantMessage()} isLast={false} onRegenerate={() => undefined} />
      </MemoryRouter>
    )
    expect(screen.queryByLabelText('重新生成')).not.toBeInTheDocument()
  })
})
