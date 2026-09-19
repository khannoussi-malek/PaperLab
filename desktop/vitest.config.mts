import { defineConfig } from 'vitest/config'

// The pure modules only, in Node with no DOM. main.ts and preload.ts need Electron: e2e/ covers them.
export default defineConfig({ test: { include: ['src/**/*.test.ts'], environment: 'node' } })
