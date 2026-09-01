import { describe, expect, it } from 'vitest'
import {
  collectionColor,
  PALETTE,
  pointColor,
  primaryCollection,
  UNCOLLECTED_COLOR
} from './pointColors'

describe('collectionColor', () => {
  it('按名称排序稳定取色（跨会话同色）', () => {
    const names = ['编程', '生活健康', '美食']
    const sorted = [...names].sort((a, b) => a.localeCompare(b))
    sorted.forEach((name, i) => {
      expect(collectionColor(names, name)).toBe(PALETTE[i % PALETTE.length])
    })
  })

  it('传入顺序不影响颜色分配', () => {
    expect(collectionColor(['a', 'b'], 'b')).toBe(collectionColor(['b', 'a'], 'b'))
  })

  it('超出色板长度时循环取色', () => {
    const names = Array.from({ length: PALETTE.length + 2 }, (_, i) => `合集${i}`)
    const sorted = [...names].sort((a, b) => a.localeCompare(b))
    expect(collectionColor(names, sorted[PALETTE.length])).toBe(PALETTE[0])
  })

  it('未合集与未知合集返回灰色', () => {
    expect(collectionColor(['a'], null)).toBe(UNCOLLECTED_COLOR)
    expect(collectionColor(['a'], '不存在')).toBe(UNCOLLECTED_COLOR)
  })
})

describe('pointColor', () => {
  it('取条目排序后第一个合集的颜色', () => {
    const all = ['编程', '生活健康']
    expect(pointColor(['生活健康', '编程'], all)).toBe(
      collectionColor(all, [...all].sort((a, b) => a.localeCompare(b))[0])
    )
  })

  it('无合集返回灰色', () => {
    expect(pointColor([], ['编程'])).toBe(UNCOLLECTED_COLOR)
  })
})

describe('primaryCollection', () => {
  it('返回排序后第一个合集', () => {
    expect(primaryCollection(['b', 'a'])).toBe('a')
  })

  it('无合集返回 null', () => {
    expect(primaryCollection([])).toBeNull()
  })
})
