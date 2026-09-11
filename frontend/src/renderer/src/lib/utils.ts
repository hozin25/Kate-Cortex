import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

export function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

/** 掩盖 URL 查询参数里的密钥值（key/token/…），保留其余部分便于辨认端点 */
export function maskSecretUrl(url: string): string {
  return url.replace(/([?&][\w-]*(?:key|token|secret|passwd|password)[\w-]*=)[^&]+/gi, '$1••••')
}
