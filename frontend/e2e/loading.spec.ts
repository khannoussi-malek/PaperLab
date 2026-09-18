import type { Page } from '@playwright/test'
import { FIRST_LINE, expect, test } from './fixtures'

const firstLine = (page: Page) => page.locator('.pdf-page[data-page="1"] .textLayer span', { hasText: FIRST_LINE })

/** Opens a hash in the same document, the way a link does: `page.goto` would reload and start everything afresh. */
const follow = (page: Page, hash: string) => page.evaluate((to) => (window.location.hash = to), hash)

test('one PDF.js worker serves the library preview and every paper opened after it', async ({
  page,
  paperId,
  secondPaperId,
}) => {
  const pdfWorkers: string[] = []
  page.on('worker', (worker) => {
    if (worker.url().includes('pdf.worker')) pdfWorkers.push(worker.url())
  })

  await page.goto('/')
  await expect(page.locator('.paper-preview canvas')).toBeVisible()
  for (const id of [paperId, secondPaperId, paperId]) {
    await follow(page, `#/papers/${id}`)
    await expect(firstLine(page)).toBeVisible()
  }
  expect(pdfWorkers).toHaveLength(1)
})
