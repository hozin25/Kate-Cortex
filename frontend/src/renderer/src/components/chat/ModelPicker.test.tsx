import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatInput } from '@renderer/components/chat/ChatInput'
import { ModelPicker } from '@renderer/components/chat/ModelPicker'
import { useToastStore } from '@renderer/stores/toast'
import type { ChatSession, ProviderCatalog } from '@renderer/types'

const session: ChatSession = {
  id: 'kc_conv_test',
  title: '测试会话',
  provider: 'glm',
  model: 'glm-4.7-flash',
  created_at: '2026-09-07T00:00:00+08:00',
  updated_at: '2026-09-07T00:00:00+08:00',
  preview: ''
}

const catalog: ProviderCatalog[] = [
  {
    name: 'glm',
    has_key: true,
    models: [
      { model: 'glm-4.7-flash', label: 'GLM-4.7-Flash', free: true, vision: false },
      { model: 'glm-4.5', label: 'GLM-4.5 旗舰', free: false, vision: false }
    ]
  },
  {
    name: 'glm-coding',
    has_key: true,
    models: [
      { model: 'glm-5.3', label: 'GLM-5.3', free: false, vision: true },
      { model: 'glm-5.1', label: 'GLM-5.1', free: false, vision: true }
    ]
  },
  {
    name: 'siliconflow',
    has_key: false,
    models: [{ model: 'Qwen/Qwen3-8B', label: 'Qwen3-8B', free: true, vision: false }]
  }
]

describe('ModelPicker', () => {
  it('徽标显示当前 provider 与模型的短名', () => {
    render(<ModelPicker session={session} catalog={catalog} onSwitch={vi.fn()} />)

    expect(screen.getByText(/GLM 智谱/)).toBeInTheDocument()
  })

  it('点击弹出目录，免费/视觉标注齐全，当前模型打勾，无 Key 的组置灰', async () => {
    const user = userEvent.setup()
    render(<ModelPicker session={session} catalog={catalog} onSwitch={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /GLM 智谱/ }))

    await waitFor(() => expect(screen.getByText('GLM-4.5 旗舰')).toBeInTheDocument())
    expect(screen.getAllByText('免费').length).toBeGreaterThan(0)
    // 视觉徽标只出现在多模态模型（glm-coding 组两枚）
    expect(screen.getAllByText('视觉').length).toBe(2)
    expect(screen.getByText('未配置 Key')).toBeInTheDocument()

    // 当前模型 glm-4.7-flash 处于选中态（弹层行含等宽 id，区别于头部徽标）
    const currentBtn = screen.getByRole('button', { name: /GLM-4\.7-Flashglm-4\.7-flash/ })
    expect(currentBtn).toBeDisabled() // 选中态按钮不可重复点
    // 无 key 组的模型按钮禁用
    expect(
      screen.getByRole('button', { name: /Qwen3-8BQwen\/Qwen3-8B/ })
    ).toBeDisabled()
  })

  it('点击其他模型回调 onSwitch 并关闭弹层', async () => {
    const onSwitch = vi.fn()
    const user = userEvent.setup()
    render(<ModelPicker session={session} catalog={catalog} onSwitch={onSwitch} />)

    await user.click(screen.getByRole('button', { name: /GLM 智谱/ }))
    await waitFor(() => expect(screen.getByText('GLM-4.5 旗舰')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /GLM-4\.5 旗舰glm-4\.5/ }))

    expect(onSwitch).toHaveBeenCalledWith('glm', 'glm-4.5')
    expect(screen.queryByText('GLM-4.5 旗舰')).not.toBeInTheDocument()
  })
})

describe('ChatInput 图片门控', () => {
  it('非视觉模型下图片按钮禁用且提示原因', () => {
    render(
      <ChatInput streaming={false} visionSupported={false} onSend={vi.fn()} onStop={vi.fn()} />
    )

    const btn = screen.getByRole('button', { name: '添加图片' })
    expect(btn).toBeDisabled()
    expect(btn.getAttribute('title')).toContain('不支持图片')
  })

  it('非视觉模型下粘贴图片被拦下并提示，不进入待发送区', async () => {
    render(
      <ChatInput streaming={false} visionSupported={false} onSend={vi.fn()} onStop={vi.fn()} />
    )
    const textarea = screen.getByRole('textbox')

    const file = new File(['x'], 'a.png', { type: 'image/png' })
    // jsdom 无 DataTransfer，fireEvent 会把附加属性直接挂到事件对象上
    fireEvent.paste(textarea, { clipboardData: { files: [file] } })

    expect(screen.queryByAltText('待发送图片 1')).not.toBeInTheDocument()
    await waitFor(() =>
      expect(
        useToastStore.getState().toasts.some((t) => t.message.includes('不支持图片'))
      ).toBe(true)
    )
  })

  it('未知视觉能力（null）不拦图片按钮', () => {
    render(
      <ChatInput streaming={false} visionSupported={null} onSend={vi.fn()} onStop={vi.fn()} />
    )

    expect(screen.getByRole('button', { name: '添加图片' })).toBeEnabled()
  })
})
