import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Tests must not inherit an operator's connected build configuration.
  define: {
    'import.meta.env.VITE_RUNTIME_MODE': JSON.stringify(''),
    'import.meta.env.VITE_API_URL': JSON.stringify(''),
    'import.meta.env.VITE_HOST_PROFILE': JSON.stringify(''),
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.{ts,tsx}'],
    setupFiles: ['./tests/setup.ts'],
    env: { VITE_RUNTIME_MODE: '', VITE_API_URL: '', VITE_HOST_PROFILE: '' },
  },
})
