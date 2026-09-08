import './assets/styles.css'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { applyTheme, getTheme } from '@renderer/lib/theme'

// 渲染前应用主题，避免亮色用户看到暗色闪屏（反之亦然）
applyTheme(getTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
