import { describe, expect, it, vi } from 'vitest'
import { createEvent, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatInput } from '@renderer/components/chat/ChatInput'
import type { Agent } from '@renderer/types'

const agents: Agent[] = [
  {
    id: 'a1',
    name: '翻译官',
    description: '中英互译',
    prompt: 'p',
    provider: null,
    model: null,
    enabled: true,
    created_at: '2026-09-13T00:00:00+08:00'
  },
  {
    id: 'a2',
    name: '写作助手',
    description: '润色与扩写',
    prompt: 'p',
    provider: 'glm-coding',
    model: 'glm-5.3',
    enabled: true,
    created_at: '2026-09-13T00:00:00+08:00'
  }
]

function renderInput(props: Partial<React.ComponentProps<typeof ChatInput>> = {}): {
  onSend: ReturnType<typeof vi.fn>
  textarea: HTMLTextAreaElement
} {
  const onSend = vi.fn()
  const view = render(
    <ChatInput
      streaming={false}
      onSend={onSend}
      onStop={vi.fn()}
      visionSupported={null}
      agents={agents}
      {...props}
    />
  )
  return { onSend, textarea: view.getByRole('textbox') as HTMLTextAreaElement }
}

describe('ChatInput / 引用 agent 菜单', () => {
  it('输入 / 弹出菜单：名称、描述、模型提示齐全', async () => {
    const user = userEvent.setup()
    const { textarea } = renderInput()

    await user.type(textarea, '/')

    expect(screen.getByRole('listbox', { name: '引用 agent' })).toBeInTheDocument()
    expect(screen.getByText('/翻译官')).toBeInTheDocument()
    expect(screen.getByText('/写作助手')).toBeInTheDocument()
    expect(screen.getByText('glm-coding · glm-5.3')).toBeInTheDocument()
    expect(screen.getByText('跟随会话模型')).toBeInTheDocument()
  })

  it('继续输入按名称与描述过滤，无匹配显示提示', async () => {
    const user = userEvent.setup()
    const { textarea } = renderInput()

    await user.type(textarea, '/写')
    expect(screen.getByText('/写作助手')).toBeInTheDocument()
    expect(screen.queryByText('/翻译官')).not.toBeInTheDocument()

    await user.type(textarea, 'x')
    expect(screen.getByText(/没有匹配的 agent/)).toBeInTheDocument()
  })

  it('↑↓ 循环高亮，Enter 选中插入 `/名称 ` 且不发送', async () => {
    const user = userEvent.setup()
    const { onSend, textarea } = renderInput()

    await user.type(textarea, '/')
    await user.keyboard('{ArrowDown}') // 高亮 → 写作助手
    await user.keyboard('{Enter}')

    expect(textarea.value).toBe('/写作助手 ')
    expect(textarea.selectionStart).toBe('/写作助手 '.length)
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(onSend).not.toHaveBeenCalled()
  })

  it('Tab 同样可选中；Esc 关闭菜单', async () => {
    const user = userEvent.setup()
    const { textarea } = renderInput()

    await user.type(textarea, '/')
    await user.keyboard('{Tab}')
    expect(textarea.value).toBe('/翻译官 ')

    // 清空后重新输入 `/翻` 打开菜单，Esc 关闭且内容保留
    await user.clear(textarea)
    await user.type(textarea, '/翻')
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(textarea.value).toBe('/翻')
  })

  it('鼠标点击菜单项选中，选中后正文照常发送（带前缀）', async () => {
    const user = userEvent.setup()
    const { onSend, textarea } = renderInput()

    await user.type(textarea, '/')
    await user.click(screen.getByText('/翻译官'))
    expect(textarea.value).toBe('/翻译官 ')

    await user.type(textarea, 'hello')
    await user.keyboard('{Enter}')
    expect(onSend).toHaveBeenCalledWith('/翻译官 hello', [])
  })

  it('无 agent 时不弹菜单', async () => {
    const user = userEvent.setup()
    const { textarea } = renderInput({ agents: [] })

    await user.type(textarea, '/')

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('菜单打开但无匹配时 Enter 回落为发送', async () => {
    const user = userEvent.setup()
    const { onSend, textarea } = renderInput()

    await user.type(textarea, '/不存在')
    expect(screen.getByText(/没有匹配的 agent/)).toBeInTheDocument()
    await user.keyboard('{Enter}')

    expect(onSend).toHaveBeenCalledWith('/不存在', [])
  })

  it('IME 组合中的 Enter 既不选中也不发送', async () => {
    const user = userEvent.setup()
    const { onSend, textarea } = renderInput()

    await user.type(textarea, '/')
    const composing = createEvent.keyDown(textarea, { key: 'Enter' })
    Object.defineProperty(composing, 'isComposing', { value: true })
    fireEvent(textarea, composing)

    expect(onSend).not.toHaveBeenCalled()
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    expect(textarea.value).toBe('/')
  })
})
