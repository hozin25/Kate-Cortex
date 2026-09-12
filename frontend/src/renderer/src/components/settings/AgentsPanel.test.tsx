import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AgentsPanel } from '@renderer/components/settings/AgentsPanel'
import { useAgentsStore } from '@renderer/stores/agents'
import { useToastStore } from '@renderer/stores/toast'
import type { Agent } from '@renderer/types'

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn()
}))

vi.mock('@renderer/api/client', () => ({ api }))

function agent(partial: Partial<Agent> = {}): Agent {
  return {
    id: 'kc_agent_t1',
    name: '翻译官',
    description: '中英互译',
    prompt: '你是资深中英互译。',
    provider: 'glm',
    model: 'glm-4.7-flash',
    enabled: true,
    created_at: '2026-09-13T00:00:00+08:00',
    ...partial
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  useAgentsStore.setState({ agents: [], loaded: false })
})

describe('AgentsPanel', () => {
  it('列出 agent：/名称、描述、指定模型、停用标记', async () => {
    api.get.mockResolvedValueOnce({
      agents: [
        agent(),
        agent({
          id: 'x2',
          name: '停用的',
          description: '闲置 agent',
          provider: null,
          model: null,
          enabled: false
        })
      ]
    })
    render(<AgentsPanel />)

    await waitFor(() => expect(screen.getByText('/翻译官')).toBeInTheDocument())
    expect(screen.getByText('中英互译')).toBeInTheDocument()
    expect(screen.getByText('glm · glm-4.7-flash')).toBeInTheDocument()
    expect(screen.getByText('已停用')).toBeInTheDocument()
  })

  it('创建：填表提交 POST，成功后清空表单并提示', async () => {
    api.get.mockResolvedValueOnce({ agents: [] })
    api.post.mockResolvedValueOnce(agent({ name: '写作助手' }))
    render(<AgentsPanel />)

    await userEvent.type(await screen.findByLabelText('Agent 名称'), '写作助手')
    await userEvent.type(screen.getByLabelText('Agent 提示词'), '你是写作助手')
    await userEvent.click(screen.getByRole('button', { name: /创建 agent/ }))

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/agents',
        expect.objectContaining({ name: '写作助手', prompt: '你是写作助手' })
      )
    )
    await waitFor(() =>
      expect(useToastStore.getState().toasts.some((t) => t.message.includes('写作助手'))).toBe(true)
    )
  })

  it('重名 409：展示后端 detail', async () => {
    api.get.mockResolvedValueOnce({ agents: [] })
    api.post.mockRejectedValueOnce(new Error('已有同名 agent「翻译官」，换个名字吧'))
    render(<AgentsPanel />)

    await userEvent.type(await screen.findByLabelText('Agent 名称'), '翻译官')
    await userEvent.type(screen.getByLabelText('Agent 提示词'), 'p')
    await userEvent.click(screen.getByRole('button', { name: /创建 agent/ }))

    await waitFor(() =>
      expect(useToastStore.getState().toasts.some((t) => t.message.includes('换个名字'))).toBe(true)
    )
  })

  it('编辑：行内展开表单，保存调用 PATCH', async () => {
    api.get.mockResolvedValueOnce({ agents: [agent()] })
    api.patch.mockResolvedValueOnce(agent({ description: '口译+笔译' }))
    render(<AgentsPanel />)
    await waitFor(() => expect(screen.getByText('/翻译官')).toBeInTheDocument())

    await userEvent.click(screen.getByLabelText('编辑 agent 翻译官'))
    const descInput = await screen.findByLabelText('Agent 描述')
    await userEvent.clear(descInput)
    await userEvent.type(descInput, '口译+笔译')
    await userEvent.click(screen.getByRole('button', { name: /保存/ }))

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        '/agents/kc_agent_t1',
        expect.objectContaining({ description: '口译+笔译' })
      )
    )
  })

  it('启停开关调用 PATCH enabled', async () => {
    api.get.mockResolvedValueOnce({ agents: [agent()] })
    api.patch.mockResolvedValueOnce(agent({ enabled: false }))
    render(<AgentsPanel />)
    await waitFor(() => expect(screen.getByText('/翻译官')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('switch'))

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith('/agents/kc_agent_t1', { enabled: false })
    )
  })

  it('删除：确认后调用 DELETE', async () => {
    api.get.mockResolvedValueOnce({ agents: [agent()] })
    api.delete.mockResolvedValueOnce(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<AgentsPanel />)
    await waitFor(() => expect(screen.getByText('/翻译官')).toBeInTheDocument())

    await userEvent.click(screen.getByLabelText('删除 agent 翻译官'))

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/agents/kc_agent_t1'))
  })
})
