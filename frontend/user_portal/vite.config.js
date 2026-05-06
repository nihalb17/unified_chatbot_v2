import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const ORCHESTRATOR = 'http://127.0.0.1:8002'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: ORCHESTRATOR,
        changeOrigin: true,
      },
      '/voice': {
        target: ORCHESTRATOR,
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
