import { boxOffset, expect, openReader, saveNoteOn, selectText, test, type Rect } from './fixtures'

test('select a passage, save a note, and find it highlighted after reload', async ({ page, request, paperId }) => {
  const line = await openReader(page, paperId)
  const card = await saveNoteOn(page, line, 'The anchor is the whole point.')
  await expect(card).toContainText('Highlights are the anchor')
  await expect(card.locator('.provenance-badge')).toHaveText('You')

  // The stored anchor (PDF.js coordinates) must sit inside the chunk PyMuPDF extracted.
  const [note] = await (await request.get(`/api/papers/${paperId}/notes`)).json()
  const [chunk] = await (await request.get(`/api/papers/${paperId}/chunks?page=1`)).json()
  const [nx0, ny0, nx1, ny1] = note.anchors[0].bbox[0] as Rect
  const [cx0, cy0, cx1, cy1] = chunk.bbox[0] as Rect
  const tolerance = 3
  expect(nx0).toBeGreaterThanOrEqual(cx0 - tolerance)
  expect(ny0).toBeGreaterThanOrEqual(cy0 - tolerance)
  expect(nx1).toBeLessThanOrEqual(cx1 + tolerance)
  expect(ny1).toBeLessThanOrEqual(cy1 + tolerance)
  expect(note.anchors[0].quoted_text).toContain('Highlights are the anchor')

  // After a reload, the highlight is drawn from stored PDF points over the same text.
  await page.reload()
  await expect(page.locator('article.note', { hasText: 'The anchor is the whole point.' })).toBeVisible()
  const highlight = page.locator(`.highlight[data-note-id="${note.id}"]`).first()
  await expect.poll(() => boxOffset(line, highlight)).toBeLessThan(4)
})

test('highlights stay on their text when zooming', async ({ page, paperId }) => {
  const line = await openReader(page, paperId)
  await saveNoteOn(page, line, 'zoom check')
  const highlight = page.locator('.highlight:not(.draft)').first()

  for (const button of ['Zoom in', 'Zoom out', 'Zoom out']) {
    await page.getByRole('button', { name: button }).click()
    await expect.poll(() => boxOffset(line, highlight)).toBeLessThan(4)
  }
})

test('editing a human note keeps the "You" badge and survives reload', async ({ page, paperId }) => {
  const line = await openReader(page, paperId)
  await saveNoteOn(page, line, 'first draft')
  const card = page.locator('article.note', { hasText: 'Highlights are the anchor' })

  await card.getByRole('button', { name: 'Edit' }).click()
  await card.getByRole('textbox', { name: 'Edit note' }).fill('second thought')
  await card.getByRole('button', { name: 'Save', exact: true }).click()

  await expect(card).toContainText('second thought')
  await expect(card.locator('.provenance-badge')).toHaveText('You')
  await page.reload()
  await expect(page.locator('article.note', { hasText: 'Highlights are the anchor' })).toContainText('second thought')
})

test('deleting a note removes its card and its highlight', async ({ page, request, paperId }) => {
  const line = await openReader(page, paperId)
  const card = await saveNoteOn(page, line, 'to be deleted')
  await expect(page.locator('.highlight')).not.toHaveCount(0)

  page.once('dialog', (dialog) => dialog.accept())
  await card.getByRole('button', { name: 'Delete' }).click()

  await expect(card).toHaveCount(0)
  await expect(page.locator('.highlight')).toHaveCount(0)
  expect(await (await request.get(`/api/papers/${paperId}/notes`)).json()).toEqual([])
})

test('a selection spanning two pages is rejected with a message', async ({ page, paperId }) => {
  const firstPageLine = await openReader(page, paperId)
  const secondPageLine = page.locator('.pdf-page[data-page="2"] .textLayer span', { hasText: 'The second page' })
  await secondPageLine.scrollIntoViewIfNeeded()
  await expect(secondPageLine).toBeVisible()

  await selectText(firstPageLine, secondPageLine)

  await expect(page.getByRole('alert')).toContainText('Select text within a single page')
  await expect(page.getByRole('textbox', { name: 'Note' })).toHaveCount(0)
})
