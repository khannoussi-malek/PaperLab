import type { Page } from '@playwright/test'
import {
  FIXTURE_FILE,
  FIXTURE_TITLE,
  expect,
  removePaperAndNotes,
  test,
  uploadAndWaitUntilReady,
} from './fixtures'

const paperRow = (page: Page, id: string) =>
  page.locator('.paper-row').filter({ has: page.locator(`a[href="#/papers/${id}"]`) })

/** True once something darker than the white sheet (text) has been drawn on the canvas. */
function hasInk(canvas: HTMLCanvasElement): boolean {
  if (canvas.width === 0) return false
  const { data } = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height)
  for (let i = 0; i < data.length; i += 4) if (data[i + 3] > 0 && data[i] < 128) return true
  return false
}

test('hovering a paper previews its first page and details beside the list', async ({ page, request, paperId }) => {
  const { page_count } = await (await request.get(`/api/papers/${paperId}`)).json()
  await page.goto('/')
  await paperRow(page, paperId).hover()

  const preview = page.locator('.paper-preview')
  await expect(preview.getByRole('link', { name: 'Open in reader' })).toHaveAttribute('href', `#/papers/${paperId}`)
  await expect(preview.getByRole('heading')).toHaveText(FIXTURE_TITLE)
  await expect(preview).toContainText(`${page_count} pages`)
  await expect.poll(() => preview.locator('canvas').evaluate(hasInk), { timeout: 15_000 }).toBe(true)
})

test('the preview follows hover and keyboard focus', async ({ page, request, paperId }) => {
  // Uploaded last, so `newestId` heads the list and is previewed by default.
  const newestId = await uploadAndWaitUntilReady(request)
  // Parallel workers upload too: keep the real list to this test's two papers, so another worker's can't head it.
  await page.route('**/api/papers', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    const response = await route.fetch()
    const papers: { id: string }[] = await response.json()
    await route.fulfill({ response, json: papers.filter((p) => p.id === paperId || p.id === newestId) })
  })
  try {
    await page.goto('/')
    const open = page.locator('.paper-preview').getByRole('link', { name: 'Open in reader' })
    await expect(open).toHaveAttribute('href', `#/papers/${newestId}`)

    await paperRow(page, paperId).hover()
    await expect(open).toHaveAttribute('href', `#/papers/${paperId}`)

    await paperRow(page, newestId).getByRole('link').focus()
    await expect(open).toHaveAttribute('href', `#/papers/${newestId}`)
  } finally {
    await removePaperAndNotes(request, newestId)
  }
})

test('upload a PDF through the UI, watch it become ready, then delete it', async ({ page, request }) => {
  await page.goto('/')
  const [uploaded] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/api/papers') && r.request().method() === 'POST'),
    page.locator('input[type="file"]').setInputFiles(FIXTURE_FILE),
  ])
  const { id } = await uploaded.json()

  try {
    const row = paperRow(page, id)
    // The library polls while ingesting; the title switches from the file name to the PDF's metadata title.
    await expect(row.locator('.status')).toHaveText('ready', { timeout: 30_000 })
    await expect(row.getByRole('link')).toHaveText(FIXTURE_TITLE)

    page.once('dialog', (dialog) => dialog.accept())
    await row.getByRole('button', { name: 'Delete' }).click()
    await expect(row).toHaveCount(0)
    expect((await request.get(`/api/papers/${id}`)).status()).toBe(404)
  } finally {
    await removePaperAndNotes(request, id)
  }
})

test('a non-PDF upload shows the error and creates no paper', async ({ page, request }) => {
  await page.goto('/')
  await page
    .locator('input[type="file"]')
    .setInputFiles({ name: 'not-a-paper.txt', mimeType: 'text/plain', buffer: Buffer.from('plain text') })

  await expect(page.getByRole('alert')).toContainText('is not a PDF')
  const papers: { title: string }[] = await (await request.get('/api/papers')).json()
  expect(papers.some((p) => p.title === 'not-a-paper')).toBe(false)
})

test('a failed first load can be retried', async ({ page }) => {
  await page.route('**/api/papers', (route) => route.abort(), { times: 1 })
  await page.goto('/')

  await expect(page.getByRole('alert')).toBeVisible()
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByRole('alert')).not.toBeVisible()
  await expect(page.getByText('Loading…')).not.toBeVisible()
})

test('the upload action is a keyboard-reachable button', async ({ page }) => {
  await page.goto('/')
  const upload = page.getByRole('button', { name: 'Upload PDFs' })
  await upload.focus()
  await expect(upload).toBeFocused()
})

test('the search box narrows the list to matching papers, and Esc brings them all back', async ({ page, paperId }) => {
  await page.goto('/')
  const search = page.getByRole('searchbox', { name: 'Search papers' })
  const row = paperRow(page, paperId)
  await expect(row).toBeVisible()
  const count = page.locator('.search-count')
  await expect(count).toHaveText('')

  await search.fill('no paper is called this')
  await expect(row).toHaveCount(0)
  await expect(page.getByText('No papers match “no paper is called this”')).toBeVisible()
  await expect(count).toHaveRole('status')
  await expect(count).toHaveText(/^0 of \d+ papers$/)
  // The preview only ever shows a paper that matches.
  await expect(page.locator('.paper-preview')).toHaveCount(0)

  // Chromium clears a search field on Esc by itself; the field's own Esc handler is for browsers that don't.
  await search.press('Escape')
  await expect(search).toHaveValue('')
  await expect(row).toBeVisible()

  // Words in any order, any case.
  await search.fill('fixture PAPERLAB')
  await expect(row).toBeVisible()
  await page.getByRole('group').getByRole('button', { name: 'Clear search' }).click()
  await expect(search).toHaveValue('')
  // The button disappears with the query; the cursor goes back to the field instead of the page.
  await expect(search).toBeFocused()
})

test("the no-match card's Clear search empties the box and puts the cursor back in it", async ({ page, paperId }) => {
  await page.goto('/')
  const search = page.getByRole('searchbox', { name: 'Search papers' })
  await search.fill('no paper is called this')
  await page.locator('.no-matches').getByRole('button', { name: 'Clear search' }).click()

  await expect(search).toHaveValue('')
  await expect(search).toBeFocused()
  await expect(paperRow(page, paperId)).toBeVisible()
})
