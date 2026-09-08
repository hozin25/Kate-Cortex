// 一次性验证（IMP-1 验收）：在真实 Chromium canvas 中执行与
// lib/imageCompress.ts 相同的压缩逻辑，输出 JPEG 供尺寸/清晰度检查。
// 运行：pnpm exec electron scripts/compress-check.cjs
const { app, BrowserWindow } = require('electron')
const { writeFile, readFile } = require('fs/promises')
const { join } = require('path')

const INPUT = join(__dirname, '..', 'release', 'test-2000px.png')
const OUT_JPEG = join(__dirname, '..', 'release', 'compressed-output.jpg')
const MAX_EDGE = 1568
const JPEG_QUALITY = 0.85

app.whenReady().then(async () => {
  try {
    const win = new BrowserWindow({ show: false })
    await win.loadURL('about:blank')
    const png = await readFile(INPUT)
    const b64 = png.toString('base64')
    const result = await win.webContents.executeJavaScript(`(async () => {
      const res = await fetch('data:image/png;base64,${b64}')
      const blob = await res.blob()
      const bitmap = await createImageBitmap(blob)
      const scale = Math.min(1, ${MAX_EDGE} / Math.max(bitmap.width, bitmap.height))
      const w = Math.max(1, Math.round(bitmap.width * scale))
      const h = Math.max(1, Math.round(bitmap.height * scale))
      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      canvas.getContext('2d').drawImage(bitmap, 0, 0, w, h)
      return { width: w, height: h, dataUrl: canvas.toDataURL('image/jpeg', ${JPEG_QUALITY}) }
    })()`)
    const raw = Buffer.from(result.dataUrl.split(',')[1], 'base64')
    await writeFile(OUT_JPEG, raw)
    console.log(
      'RESULT ' +
        JSON.stringify({
          input_bytes: png.length,
          output_bytes: raw.length,
          out_width: result.width,
          out_height: result.height,
          reduction: ((1 - raw.length / png.length) * 100).toFixed(1) + '%'
        })
    )
  } catch (err) {
    console.error('FAILED', err)
  } finally {
    app.quit()
  }
})
