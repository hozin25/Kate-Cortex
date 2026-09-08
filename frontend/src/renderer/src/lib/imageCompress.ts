/**
 * 发送前图片压缩：最长边 ≤1568px、JPEG quality 0.85。
 * gif 透传（canvas 会丢动画）；小图（≤1568px 且 <300KB）透传。
 */

const MAX_EDGE = 1568
const PASS_THROUGH_BYTES = 300 * 1024
const JPEG_QUALITY = 0.85

export async function compressImage(file: File): Promise<string> {
  if (file.type === 'image/gif') return readAsDataUrl(file)
  if (file.size < PASS_THROUGH_BYTES) {
    // 小图仍需检查尺寸；先解码（webp 小图例外：canvas 输出 jpeg 通常更小，但仍透传）
    const dims = await decodeSize(file)
    if (dims && Math.max(dims.width, dims.height) <= MAX_EDGE) return readAsDataUrl(file)
  }
  const bitmap = await createBitmap(file)
  if (!bitmap) return readAsDataUrl(file)
  try {
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height))
    const w = Math.max(1, Math.round(bitmap.width * scale))
    const h = Math.max(1, Math.round(bitmap.height * scale))
    const canvas = document.createElement('canvas')
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')
    if (!ctx) return readAsDataUrl(file)
    ctx.drawImage(bitmap, 0, 0, w, h)
    const out = canvas.toDataURL('image/jpeg', JPEG_QUALITY)
    // 极端情况（本来就极小的 png）压缩后可能更大，取小者
    const original = await readAsDataUrl(file)
    return out.length < original.length ? out : original
  } finally {
    bitmap.close()
  }
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

async function createBitmap(file: File): Promise<ImageBitmap | null> {
  try {
    return await createImageBitmap(file)
  } catch {
    return null
  }
}

async function decodeSize(file: File): Promise<{ width: number; height: number } | null> {
  const bitmap = await createBitmap(file)
  if (!bitmap) return null
  try {
    return { width: bitmap.width, height: bitmap.height }
  } finally {
    bitmap.close()
  }
}
