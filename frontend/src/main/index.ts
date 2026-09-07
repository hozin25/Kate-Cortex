import { app, BrowserWindow, dialog, shell } from 'electron'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'
import { startSidecar, type SidecarHandle } from './sidecar'

let sidecar: SidecarHandle | null = null

function createWindow(): void {
  const mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    show: false,
    autoHideMenuBar: true,
    ...(process.platform === 'linux' ? { icon } : {}),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      // 后端端口与鉴权 token 经命令行传给 preload（DESIGN §2.2 / §9 本地鉴权）
      additionalArguments: [
        `--kate-port=${sidecar?.port ?? 1738}`,
        `--kate-token=${sidecar?.token ?? ''}`
      ]
    }
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

// 双开保护：第二实例直接退出，避免重复拉起 sidecar
if (!app.requestSingleInstanceLock()) {
  app.quit()
}

app.whenReady().then(async () => {
  electronApp.setAppUserModelId('com.katecortex.app')

  app.on('second-instance', () => {
    const win = BrowserWindow.getAllWindows()[0]
    if (win) {
      if (win.isMinimized()) win.restore()
      win.focus()
    }
  })

  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // 启动时序：sidecar 就绪 → 再建窗口（避免白屏与连接拒绝）
  try {
    sidecar = await startSidecar()
  } catch (err) {
    dialog.showErrorBox(
      'Kate-Cortex 后端启动失败',
      `${err instanceof Error ? err.message : String(err)}\n\n请重试；若持续失败请查看日志。`
    )
    app.quit()
    return
  }

  createWindow()

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// 退出清理：树杀后端（先等它善终，最多 5s）
app.on('will-quit', (event) => {
  if (!sidecar) return
  event.preventDefault()
  const handle = sidecar
  sidecar = null
  const timer = setTimeout(() => app.exit(0), 5000)
  void handle.stop().finally(() => {
    clearTimeout(timer)
    app.exit(0)
  })
})
