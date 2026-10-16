import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 开发期通过代理访问后端，避免 CORS；生产期构建产物由 FastAPI 直接托管
const BACKEND_TARGET = process.env.VITE_BACKEND_TARGET || 'http://127.0.0.1:8080'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // 只绑 IPv4 回环。同一工作区的 sentiment_analyse 项目把 dev server 绑在
    // IPv6 侧并占着 5173/5174/5175，而 Windows 解析 localhost 时优先走 ::1，
    // 因此用 http://localhost:<port> 会打到那个项目上。绑 127.0.0.1 后
    // Vite 只提示 http://127.0.0.1:5175/，照提示打开即本项目。
    // 需要局域网（手机）联调时临时加 --host：npm run dev -- --host
    host: '127.0.0.1',
    port: 5175,
    // 端口被占用时直接报错退出，不静默漂移到 5176、5177……
    // 否则 README 写的地址会与实际不符
    strictPort: true,
    proxy: {
      '/api': { target: BACKEND_TARGET, changeOrigin: true },
      '/internal': { target: BACKEND_TARGET, changeOrigin: true },
      '/healthz': { target: BACKEND_TARGET, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1600,
    rollupOptions: {
      output: {
        // 拆包：Element Plus 体积较大，单独成 chunk 利于缓存。
        // echarts 与 markdown 相关依赖在 T-26（问答渲染）/ T-29（看板）引入时再追加拆分，
        // 否则会因未被引用而产出空 chunk。
        manualChunks: {
          'element-plus': ['element-plus', '@element-plus/icons-vue'],
        },
      },
    },
  },
})
