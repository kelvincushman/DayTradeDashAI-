import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const API = 'http://localhost:8767'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3456,
    host: '0.0.0.0',
    proxy: {
      '/research':  { target: API, changeOrigin: true },
      '/news':      { target: API, changeOrigin: true },
      '/candidates':{ target: API, changeOrigin: true },
      '/settings':  { target: API, changeOrigin: true },
      '/trades':    { target: API, changeOrigin: true },
      '/alpaca':    { target: API, changeOrigin: true },
      '/history':   { target: API, changeOrigin: true },
      '/health':    { target: API, changeOrigin: true },
      '/backtest': { target: API, changeOrigin: true },
    }
  }
})
