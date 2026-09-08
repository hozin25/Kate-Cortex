// 轻量更新检查（IMP-9）：比对 GitHub Releases 最新版本号，提示人工下载。
// 国内网络现实：失败/超时静默跳过（每会话最多一次），不引入 electron-updater。
import { app, dialog, shell } from 'electron'

const RELEASES_API = 'https://api.github.com/repos/hozin25/Kate-Cortex/releases/latest'
const TIMEOUT_MS = 8000

export function scheduleUpdateCheck(delayMs = 10_000): void {
  if (process.env['KATE_UPDATE_CHECK'] === '0') return
  setTimeout(() => {
    void checkForUpdate().catch(() => undefined)
  }, delayMs)
}

async function checkForUpdate(): Promise<void> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  let tag: string
  let htmlUrl: string
  try {
    const res = await fetch(RELEASES_API, {
      signal: controller.signal,
      headers: { 'User-Agent': 'Kate-Cortex-Update-Check' }
    })
    if (!res.ok) return
    const data = (await res.json()) as { tag_name?: string; html_url?: string }
    if (!data.tag_name) return
    tag = data.tag_name.replace(/^v/, '')
    htmlUrl = data.html_url || 'https://github.com/hozin25/Kate-Cortex/releases/latest'
  } finally {
    clearTimeout(timer)
  }
  const current = app.getVersion()
  if (compareVersions(tag, current) <= 0) return
  const choice = await dialog.showMessageBox({
    type: 'info',
    title: '发现新版本',
    message: `Kate-Cortex ${tag} 已发布（当前 ${current}）`,
    detail: '点击「前往下载」打开发布页，手动下载安装包覆盖安装即可。',
    buttons: ['前往下载', '暂不更新'],
    defaultId: 0
  })
  if (choice.response === 0) {
    void shell.openExternal(htmlUrl)
  }
}

export function compareVersions(a: string, b: string): number {
  const pa = a.split('.').map(Number)
  const pb = b.split('.').map(Number)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0)
    if (diff !== 0) return diff
  }
  return 0
}
