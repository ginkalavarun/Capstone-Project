import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // The backend CORS allowlist (D10) includes http://localhost:5173 —
    // keep the two in sync if this port ever changes.
    port: 5173,
  },
  test: {
    // Vitest (jsdom environment) — the frontend unit/integration suite.
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    include: ['src/**/*.test.{js,jsx}'],
  },
})
