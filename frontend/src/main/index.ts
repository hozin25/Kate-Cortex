import { app, BrowserWindow, dialog, globalShortcut, shell } from 'electron'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'
import { startSidecar, type SidecarHandle } from './sidecar'
import { scheduleUpdateCheck } from './update-check'

let sidecar: SidecarHandle | null = null
let captureWindow: BrowserWindow | null = null
let quitting = false

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

  // 主窗口关闭 → 销毁速记窗，让 window-all-closed 正常触发退出
  // （速记窗常驻隐藏，否则应用会隐形驻留）
  mainWindow.on('closed', () => {
    if (captureWindow && !captureWindow.isDestroyed()) captureWindow.destroy()
    captureWindow = null
  })
}

// ── 全局速记窗（CAPTURE_PLAN.md §2）：热键唤起的无边框小窗，加载 #/capture ──

function createCaptureWindow(): void {
  captureWindow = new BrowserWindow({
    width: 460,
    height: 360,
    show: false,
    frame: false,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      additionalArguments: [
        `--kate-port=${sidecar?.port ?? 1738}`,
        `--kate-token=${sidecar?.token ?? ''}`
      ]
    }
  })
  // 「关闭」= 隐藏：热键随时再唤起；应用退出时由 quitting 放行
  captureWindow.on('close', (event) => {
    if (!quitting) {
      event.preventDefault()
      captureWindow?.hide()
    }
  })
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    void captureWindow.loadURL(`${process.env['ELECTRON_RENDERER_URL']}#/capture`)
  } else {
    void captureWindow.loadFile(join(__dirname, '../renderer/index.html'), {
      hash: 'capture'
    })
  }
}

function toggleCaptureWindow(): void {
  if (!captureWindow || captureWindow.isDestroyed()) createCaptureWindow()
  const win = captureWindow
  if (!win) return
  if (win.isVisible() && win.isFocused()) {
    win.hide()
  } else {
    win.center()
    win.show()
    win.focus()
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

  // 全局速记热键（CAPTURE_PLAN.md §2）；被占用时降级为仅应用内可用
  createCaptureWindow()
  if (!globalShortcut.register('CommandOrControl+Shift+K', toggleCaptureWindow)) {
    console.warn('全局快捷键 Ctrl+Shift+K 注册失败（可能被其他应用占用），速记窗仅可从应用内唤起')
  }

  // 启动 10s 后做一次轻量更新检查（不阻塞首屏；失败静默）
  scheduleUpdateCheck()

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// 退出清理：注销全局热键；树杀后端（先等它善终，最多 5s）
app.on('will-quit', (event) => {
  quitting = true
  globalShortcut.unregisterAll()
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
