import { describe, expect, it } from 'vitest'
import { maskSecretUrl } from './utils'

describe('maskSecretUrl', () => {
  it('掩盖 key 参数值，保留端点结构', () => {
    expect(maskSecretUrl('https://mcp.amap.com/mcp?key=abc123-secret')).toBe(
      'https://mcp.amap.com/mcp?key=••••'
    )
  })

  it('支持常见密钥参数名与多参数', () => {
    expect(maskSecretUrl('https://x.cn/mcp?token=t1&city=bj')).toBe(
      'https://x.cn/mcp?token=••••&city=bj'
    )
    expect(maskSecretUrl('https://x.cn/mcp?api_key=k&foo=bar')).toBe(
      'https://x.cn/mcp?api_key=••••&foo=bar'
    )
  })

  it('无查询参数或无关参数时原样返回', () => {
    expect(maskSecretUrl('https://mcp.example.com/mcp')).toBe('https://mcp.example.com/mcp')
    expect(maskSecretUrl('https://x.cn/mcp?city=bj')).toBe('https://x.cn/mcp?city=bj')
  })
})
