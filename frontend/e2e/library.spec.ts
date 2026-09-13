import { FIXTURE_FILE, FIXTURE_TITLE, expect, removePaperAndNotes, test } from './fixtures'

test('upload a PDF through the UI, watch it become ready, then delete it', async ({ page, request }) => {
  await page.goto('/')
  const [uploaded] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/api/papers') && r.request().method() === 'POST'),
    page.locator('input[type="file"]').setInputFiles(FIXTURE_FILE),
  ])
  const { id } = await uploaded.json()

  try {
    const row = page.locator('.paper-row').filter({ has: page.locator(`a[href="#/papers/${id}"]`) })
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
