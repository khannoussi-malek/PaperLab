// Copies the speech detector's model, worklet and wasm out of node_modules into public/voice/ (git-ignored), where
// the page loads them from. Runs before `npm run dev` and `npm run build`.
import { copyFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const modules = fileURLToPath(new URL('../node_modules/', import.meta.url))
const out = fileURLToPath(new URL('../public/voice/', import.meta.url))
const vad = `${modules}@ricky0123/vad-web/dist/`
const ort = `${modules}onnxruntime-web/dist/`
const files = [
  [`${vad}silero_vad_v5.onnx`, 'silero_vad_v5.onnx'],
  [`${vad}vad.worklet.bundle.min.js`, 'vad.worklet.bundle.min.js'],
  [`${ort}ort-wasm-simd-threaded.wasm`, 'ort-wasm-simd-threaded.wasm'],
  [`${ort}ort-wasm-simd-threaded.mjs`, 'ort-wasm-simd-threaded.mjs'],
]

mkdirSync(out, { recursive: true })
for (const [from, name] of files) copyFileSync(from, `${out}${name}`)
console.log(`copied ${files.length} voice assets to public/voice/`)
