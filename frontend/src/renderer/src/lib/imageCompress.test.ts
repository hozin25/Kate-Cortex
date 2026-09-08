import { beforeEach, describe, expect, it, vi } from 'vitest'
import { compressImage } from './imageCompress'

// jsdom 无 canvas/createImageBitmap，编译码逻辑走人工验证；这里只测透传分支
const gifDataUrl = 'data:image/gif;base64,R0lGODlhAQABAAAAACw='
const pngDataUrl = 'data:image/png;base64,iVBORw0KGgo='

function makeFile(type: string, size: number, dataUrl: string): File {
  const blob = new Blob([new Uint8Array(size)], { type })
  const file = new File([blob], 'img', { type })
  vi.spyOn(FileReader.prototype, 'readAsDataURL').mockImplementation(function (this: FileReader) {
    Object.defineProperty(this, 'result', { value: dataUrl })
    this.onload?.({} as ProgressEvent<FileReader>)
  })
  return file
}

describe('compressImage 透传分支', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('gif 直接透传，不尝试解码', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn(() => Promise.reject(new Error('no'))))
    try {
      const file = makeFile('image/gif', 1024, gifDataUrl)
      await expect(compressImage(file)).resolves.toBe(gifDataUrl)
      expect(createImageBitmap).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('小图（<300KB 且解码不可用）透传 data URL', async () => {
    vi.stubGlobal('createImageBitmap', undefined)
    try {
      const file = makeFile('image/png', 2048, pngDataUrl)
      await expect(compressImage(file)).resolves.toBe(pngDataUrl)
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
