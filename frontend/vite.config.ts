import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  return {
    plugins: [react()],
    server: {
      // Preview is frontend-only. Only explicitly connected development keeps
      // the existing local API proxy; this configuration starts no backend.
      proxy: env.VITE_RUNTIME_MODE === 'connected' ? {
        '/api': { target: 'http://localhost:8000', changeOrigin: true },
      } : undefined,
    },
    build: { outDir: 'dist' },
  }
})
