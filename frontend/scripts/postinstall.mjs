// postinstall：桌面端需要 electron-builder install-app-deps 为 Electron 重编原生依赖；
// Web / CI 构建（Vercel，ELECTRON_SKIP_BINARY_DOWNLOAD=1，无 Electron 二进制）跳过。
import { spawnSync } from 'node:child_process'

if (process.env.ELECTRON_SKIP_BINARY_DOWNLOAD) {
  console.log('[postinstall] web 构建，跳过 electron-builder install-app-deps')
  process.exit(0)
}

const result = spawnSync('electron-builder', ['install-app-deps'], {
  stdio: 'inherit',
  shell: true
})
process.exit(result.status ?? 1)
