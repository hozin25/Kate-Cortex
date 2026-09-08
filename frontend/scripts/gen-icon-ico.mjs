// 从 512px PNG 生成多尺寸 ICO（16/24/32/48/64/128/256），避免 electron-builder
// 的 png→ico 自动转换静默失败。用法：node scripts/gen-icon-ico.mjs icon.png icon.ico
import { readFileSync, writeFileSync } from 'node:fs'

const [src, dst = 'icon.ico'] = process.argv.slice(2)
const png = readFileSync(src)
const sizes = [16, 24, 32, 48, 64, 128, 256]

// PNG 直接内嵌（Vista+ 支持 PNG 压缩的 ICO 条目）；小尺寸同样内嵌 512px PNG，
// Windows 会自行缩放——为保证小尺寸观感这里退而求其次（MVP 可接受）
const header = Buffer.alloc(6)
header.writeUInt16LE(0, 0)
header.writeUInt16LE(1, 2) // type: icon
header.writeUInt16LE(sizes.length, 4)

const dir = Buffer.alloc(16 * sizes.length)
const now = Date.now()
let offset = 6 + dir.length
const entries = []
sizes.forEach((size, i) => {
  dir.writeUInt8(size === 256 ? 0 : size, i * 16)
  dir.writeUInt8(size === 256 ? 0 : size, i * 16 + 1)
  dir.writeUInt16LE(1, i * 16 + 4) // planes
  dir.writeUInt16LE(32, i * 16 + 6) // bpp
  dir.writeUInt32LE(png.length, i * 16 + 8)
  dir.writeUInt32LE(offset, i * 16 + 12)
  entries.push({ offset, length: png.length })
  offset += png.length
})

writeFileSync(dst, Buffer.concat([header, dir, ...sizes.map(() => png)]))
console.log(`wrote ${dst} (${offset} bytes, ${sizes.length} entries)`)
