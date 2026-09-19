// Renders desktop/build's icons from the favicon with Playwright's Chromium (`npx playwright install chromium` once):
// icon.png (1024 px) for the installers, and macOS's menu-bar template images (black on transparent, 16 and 32 px).
// Run `npm run icons`, then commit the three PNGs.
import { mkdir, readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'

const out = (file) => fileURLToPath(new URL(`../build/${file}`, import.meta.url))
const favicon = await readFile(new URL('../../frontend/public/favicon.svg', import.meta.url), 'utf8')
// The favicon's page and lines as a silhouette: a template image is only its alpha, and macOS colours it.
const template = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="10 10 44 44">
  <rect x="17.5" y="12.5" width="29" height="39" rx="3" fill="none" stroke="#000" stroke-width="3"/>
  <rect x="21" y="19" width="22" height="3" rx="1.5"/>
  <rect x="21" y="28" width="22" height="3" rx="1.5"/>
  <rect x="21" y="37" width="22" height="3" rx="1.5"/>
  <rect x="21" y="44" width="14" height="3" rx="1.5"/>
</svg>`

await mkdir(fileURLToPath(new URL('../build/', import.meta.url)), { recursive: true })
const browser = await chromium.launch()
async function render(svg, size, file) {
  const page = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 })
  const src = `data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`
  await page.setContent(`<body style="margin:0"><img src="${src}" style="display:block;width:${size}px;height:${size}px"></body>`)
  await page.screenshot({ path: out(file), omitBackground: true })
  await page.close()
}
await render(favicon, 1024, 'icon.png')
await render(template, 16, 'trayTemplate.png')
await render(template, 32, 'trayTemplate@2x.png')
await browser.close()
