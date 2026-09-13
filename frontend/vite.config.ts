/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // API_URL is http://api:8000 inside compose; the host default is for `npm run dev` on the host.
    proxy: { '/api': process.env.API_URL ?? 'http://localhost:8000' },
  },
  test: { include: ['src/**/*.test.ts'] },
})
