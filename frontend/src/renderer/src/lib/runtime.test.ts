import { describe, expect, it } from 'vitest'
import { isElectron, kateRuntime } from './runtime'

describe('runtime', () => {
  it('无 preload 注入时（Web/测试环境）isElectron 为 false', () => {
    expect(isElectron).toBe(false)
    expect(kateRuntime()).toBeUndefined()
  })

  it('kateRuntime() 动态反映 window.api 注入值', () => {
    ;(window as { api?: unknown }).api = { kateRuntime: { apiPort: 1744, apiToken: 't' } }
    expect(kateRuntime()).toEqual({ apiPort: 1744, apiToken: 't' })
    delete (window as { api?: unknown }).api
    expect(kateRuntime()).toBeUndefined()
  })
})
