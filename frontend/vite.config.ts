// 纯 Web 构建（Vercel 静态站 / 浏览器直开）：与 electron.vite.config.ts 的
// renderer 段保持一致（alias + react + tailwind），Electron 桌面端不走这份配置。
// API 默认同源 /api（vercel.json 把 /api/* 重写到 serverless 函数），
// 可用环境变量 VITE_API_BASE 覆盖指向任意远程后端。
import { resolve } from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  root: resolve('src/renderer'),
  resolve: {
    alias: { '@renderer': resolve('src/renderer/src') }
  },
  plugins: [
    react(),
    tailwindcss(),
    {
      name: 'web-relax-csp',
      transformIndexHtml(html: string): string {
        // 桌面端 CSP 只放行 127.0.0.1:1738；Web 版后端走同源 /api，
        // 并保留对任意本机端口 sidecar 的直连能力（浏览器本机调试）
        return html.replace(
          "connect-src 'self' http://127.0.0.1:1738 http://localhost:1738",
          "connect-src 'self' http://127.0.0.1:* http://localhost:*"
        )
      }
    }
  ],
  define: {
    'import.meta.env.VITE_API_BASE': JSON.stringify(process.env.VITE_API_BASE || '/api')
  },
  // 本地 pnpm dev:web 时把同源 /api 代理到本机 sidecar，免 CORS
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:1738'
    }
  },
  build: {
    outDir: resolve('dist'),
    emptyOutDir: true
  }
})
