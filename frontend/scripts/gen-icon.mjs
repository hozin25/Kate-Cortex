// 生成 512x512 品牌图标（无第三方依赖，纯 zlib PNG 编码）
// 用法：node scripts/gen-icon.mjs [输出路径]
import { deflateSync } from 'node:zlib'
import { writeFileSync } from 'node:fs'

const SIZE = 512
const out = process.argv[2] ?? 'icon.png'

// oklch 近似换算的 sRGB（手调）：indigo #5b5bd6 → violet #a55fd6
const C1 = [91, 91, 214] // aurora-indigo
const C2 = [165, 95, 214] // aurora-violet
const BG = [16, 15, 26] // ink-950 深底
const WHITE = [255, 255, 255]

const clamp01 = (v) => Math.min(1, Math.max(0, v))
const mix = (a, b, t) => [
  Math.round(a[0] + (b[0] - a[0]) * t),
  Math.round(a[1] + (b[1] - a[1]) * t),
  Math.round(a[2] + (b[2] - a[2]) * t)
]

// 圆角矩形 SDF（带 1px 抗锯齿）
function roundedRectSDF(x, y, cx, cy, hw, hh, r) {
  const dx = Math.abs(x - cx) - (hw - r)
  const dy = Math.abs(y - cy) - (hh - r)
  const ax = Math.max(dx, 0)
  const ay = Math.max(dy, 0)
  return Math.hypot(ax, ay) + Math.min(Math.max(dx, dy), 0) - r
}

// 点到线段距离
function segDist(px, py, x1, y1, x2, y2) {
  const vx = x2 - x1
  const vy = y2 - y1
  const wx = px - x1
  const wy = py - y1
  const t = clamp01((wx * vx + wy * vy) / (vx * vx + vy * vy))
  return Math.hypot(px - (x1 + t * vx), py - (y1 + t * vy))
}

// "K" 三笔：竖笔 + 上斜 + 下斜（粗描边）
const STROKE = 30
const K = [
  [186, 160, 186, 352], // 竖
  [186, 256, 300, 160], // 上斜
  [186, 256, 312, 352] // 下斜
]

const raw = Buffer.alloc(SIZE * (SIZE * 4 + 1))
for (let y = 0; y < SIZE; y++) {
  const rowStart = y * (SIZE * 4 + 1)
  raw[rowStart] = 0 // filter: none
  for (let x = 0; x < SIZE; x++) {
    // 全幅深底
    let color = BG
    // 圆角矩形（略出血到边缘，占满）+ 对角渐变
    const d = roundedRectSDF(x + 0.5, y + 0.5, 256, 256, 256, 256, 104)
    if (d <= 0.5) {
      const t = clamp01((x + y) / (2 * SIZE) + 0.06)
      color = mix(C1, C2, t)
    } else if (d < 1.5) {
      const t = clamp01((x + y) / (2 * SIZE) + 0.06)
      color = mix(BG, mix(C1, C2, t), 1 - (d - 0.5))
    }
    // 白色 K（覆盖在渐变上，带抗锯齿）
    let kd = Infinity
    for (const [x1, y1, x2, y2] of K) kd = Math.min(kd, segDist(x + 0.5, y + 0.5, x1, y1, x2, y2))
    if (kd < STROKE) color = WHITE
    else if (kd < STROKE + 1) color = mix(WHITE, color, kd - STROKE)
    const o = rowStart + 1 + x * 4
    raw[o] = color[0]
    raw[o + 1] = color[1]
    raw[o + 2] = color[2]
    raw[o + 3] = 255
  }
}

function crc32(buf) {
  let c
  const table = crc32.table ??= Array.from({ length: 256 }, (_, n) => {
    c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    return c >>> 0
  })
  c = 0xffffffff
  for (const b of buf) c = table[(c ^ b) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body))
  return Buffer.concat([len, body, crc])
}

const ihdr = Buffer.alloc(13)
ihdr.writeUInt32BE(SIZE, 0)
ihdr.writeUInt32BE(SIZE, 4)
ihdr[8] = 8 // bit depth
ihdr[9] = 6 // RGBA
const png = Buffer.concat([
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  chunk('IHDR', ihdr),
  chunk('IDAT', deflateSync(raw, { level: 9 })),
  chunk('IEND', Buffer.alloc(0))
])
writeFileSync(out, png)
console.log(`wrote ${out} (${png.length} bytes)`)
