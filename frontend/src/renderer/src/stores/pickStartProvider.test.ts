import { describe, expect, it } from 'vitest'
import { pickStartProvider } from './chat'
import type { AppSettings } from '../types'

function settings(partial: Partial<AppSettings>): AppSettings {
  return {
    provider_keys: {},
    default_provider: 'glm',
    default_model: 'glm-4.7-flash',
    rag_default: true,
    memory_enabled: true,
    embedding_provider: 'glm',
    embedding_model: 'embedding-3',
    embedding_api_key: null,
    mcp_url: null,
    export_dir: null,
    vault_path: null,
    ...partial
  } as AppSettings
}

describe('pickStartProvider', () => {
  it('默认服务商已配置 key 时直接使用', () => {
    const s = settings({ default_provider: 'glm', provider_keys: { glm: 'k' } })
    expect(pickStartProvider(s)).toBe('glm')
  })

  it('默认服务商无 key 时回退到任一已配置的服务商', () => {
    const s = settings({ default_provider: 'glm', provider_keys: { 'glm-coding': 'k' } })
    expect(pickStartProvider(s)).toBe('glm-coding')
  })

  it('多个已配置时按回退顺序取第一个', () => {
    const s = settings({
      default_provider: 'glm',
      provider_keys: { deepseek: 'k', modelscope: 'k2' }
    })
    expect(pickStartProvider(s)).toBe('modelscope')
  })

  it('全部未配置时维持默认（由后端给出明确报错）', () => {
    expect(pickStartProvider(settings({}))).toBe('glm')
    expect(pickStartProvider(null)).toBe('deepseek')
  })
})
