import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ModelPicker } from '@renderer/components/chat/ModelPicker'
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
      { model: 'glm-4.7-flash', label: 'GLM-4.7-Flash', free: true },
      { model: 'glm-4.5', label: 'GLM-4.5 旗舰', free: false }
    ]
  },
  {
    name: 'siliconflow',
    has_key: false,
    models: [{ model: 'Qwen/Qwen3-8B', label: 'Qwen3-8B', free: true }]
  }
]

function stubModelsApi(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ providers: catalog })
      }) as unknown as Response
    )
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('ModelPicker', () => {
  it('徽标显示当前 provider 与模型的短名', () => {
    stubModelsApi()
    render(<ModelPicker session={session} onSwitch={vi.fn()} />)

    expect(screen.getByText(/GLM 智谱/)).toBeInTheDocument()
  })

  it('点击弹出目录，免费模型带标注，当前模型打勾，无 Key 的组置灰', async () => {
    stubModelsApi()
    const user = userEvent.setup()
    render(<ModelPicker session={session} onSwitch={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /GLM 智谱/ }))

    await waitFor(() => expect(screen.getByText('GLM-4.5 旗舰')).toBeInTheDocument())
    expect(screen.getAllByText('免费').length).toBeGreaterThan(0)
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
    stubModelsApi()
    const onSwitch = vi.fn()
    const user = userEvent.setup()
    render(<ModelPicker session={session} onSwitch={onSwitch} />)

    await user.click(screen.getByRole('button', { name: /GLM 智谱/ }))
    await waitFor(() => expect(screen.getByText('GLM-4.5 旗舰')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /GLM-4.5 旗舰/ }))

    expect(onSwitch).toHaveBeenCalledWith('glm', 'glm-4.5')
    expect(screen.queryByText('GLM-4.5 旗舰')).not.toBeInTheDocument()
  })
})
