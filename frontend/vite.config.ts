/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig, type Plugin } from 'vite'

// PDF.js's image decoders (CCITT fax, JBIG2, JPEG 2000, colour profiles), at the /pdfjs-wasm/ that src/features/reader/pdfjs.ts
// gives it as wasmUrl. PDF.js asks for them by fixed name, so they are served as they are, not hashed by an import.
const PDFJS_WASM = fileURLToPath(new URL('./node_modules/pdfjs-dist/wasm/', import.meta.url))
const pdfjsWasm = (): Plugin => ({
  name: 'pdfjs-wasm',
  configureServer(server) {
    server.middlewares.use('/pdfjs-wasm', (req, res, next) => {
      const name = (req.url ?? '').replace(/^\/|\?.*$/g, '')
      if (!readdirSync(PDFJS_WASM).includes(name)) return next()
      res.setHeader('Content-Type', name.endsWith('.wasm') ? 'application/wasm' : 'text/javascript')
      res.end(readFileSync(PDFJS_WASM + name))
    })
  },
  generateBundle() {
    for (const name of readdirSync(PDFJS_WASM).filter((n) => !n.startsWith('LICENSE')))
      this.emitFile({ type: 'asset', fileName: `pdfjs-wasm/${name}`, source: readFileSync(PDFJS_WASM + name) })
  },
})

export default defineConfig({
  plugins: [react(), tailwindcss(), pdfjsWasm()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  // The hand tracker's bundle has no imports of its own, so it is served as is: pre-bundling would only make the dev
  // server discover it on first use and reload the page in the middle of hands mode.
  // The speech detector is imported on first use of the microphone: listing it here pre-bundles it at startup, so the
  // dev server doesn't find it mid-session and reload the page.
  optimizeDeps: { include: ['@ricky0123/vad-web'], exclude: ['@mediapipe/tasks-vision'] },
  server: {
    // API_URL is http://api:8000 inside compose; the host default is for `npm run dev` on the host.
    // ws: the voice panel's WebSocket (/api/voice/ws) goes through the same proxy.
    proxy: { '/api': { target: process.env.API_URL ?? 'http://localhost:8000', ws: true } },
  },
  test: {
    include: ['src/**/*.test.{ts,tsx}', 'e2e/**/*.vitest.ts'],
    setupFiles: ['./src/test/setup.ts'],
  },
})
