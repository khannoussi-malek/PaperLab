// Copies the README screenshots from .github/assets into public/shots/: each PNG as-is (for social previews, which
// want PNG or JPEG) and as a 1600-px WebP for pages, about a tenth of the size. Runs before every dev and build.
import { mkdirSync, readdirSync, copyFileSync } from 'node:fs'
import sharp from 'sharp'

const from = new URL('../../.github/assets/', import.meta.url)
const to = new URL('../public/shots/', import.meta.url)
mkdirSync(to, { recursive: true })

const pngs = readdirSync(from).filter((name) => name.endsWith('.png'))
await Promise.all(
  pngs.map(async (name) => {
    copyFileSync(new URL(name, from), new URL(name, to))
    await sharp(new URL(name, from).pathname)
      .resize({ width: 1600, withoutEnlargement: true })
      .webp({ quality: 78 })
      .toFile(new URL(name.replace(/\.png$/, '.webp'), to).pathname)
  }),
)
console.log(`shots: ${pngs.length} screenshots, PNG and WebP`)
