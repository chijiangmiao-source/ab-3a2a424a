import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发环境把 /api 代理到本地 FastAPI；生产由 nginx 代理
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000'
    }
  }
})
