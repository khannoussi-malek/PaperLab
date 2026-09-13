import { backgroundOf } from './computedStyle'
import { expect, openReader, saveNoteOn, selectText, test } from './fixtures'

test('the hover card stays open on the way to it and manages the note without the panel', async ({
  page,
  request,
  paperId,
}) => {
  const line = await openReader(page, paperId)
  await saveNoteOn(page, line, 'first thought')
  const [note] = await (await request.get(`/api/papers/${paperId}/notes`)).json()
  const panelCard = page.locator(`article.note[data-note-id="${note.id}"]`)
  const highlight = page.locator(`.highlight[data-note-id="${note.id}"]`).first()

  await line.hover()
  const hoverCard = page.locator('.note-hover-card')
  await expect(hoverCard).toContainText('first thought')

  // Travel from the highlight down into the card: it must not close on the way.
  const box = (await hoverCard.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + 12, { steps: 10 })
  await page.waitForTimeout(600) // twice the close delay
  await expect(hoverCard).toBeVisible()

  await hoverCard.getByRole('button', { name: 'Edit' }).click()
  await hoverCard.getByRole('textbox', { name: 'Edit note' }).fill('second thought')
  // The pointer wanders off mid-edit: the card must stay.
  await page.mouse.move(5, 400)
  await page.waitForTimeout(600)
  await expect(hoverCard).toBeVisible()
  await hoverCard.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(panelCard).toContainText('second thought')

  await hoverCard.getByLabel('Custom colour').fill('#ff00aa')
  await expect.poll(() => backgroundOf(highlight)).toBe('rgba(255, 0, 170, 0.4)')

  page.once('dialog', (dialog) => dialog.accept())
  await hoverCard.getByRole('button', { name: 'Delete' }).click()
  await expect(panelCard).toHaveCount(0)
  await expect(hoverCard).toHaveCount(0)
  expect(await (await request.get(`/api/papers/${paperId}/notes`)).json()).toEqual([])
})

test('the hover card stays open while any of its overlapping notes is still being edited', async ({
  page,
  request,
  paperId,
}) => {
  let line = await openReader(page, paperId)
  const [chunk] = await (await request.get(`/api/papers/${paperId}/chunks?page=1`)).json()
  for (const body of ['overlap A', 'overlap B']) {
    const res = await request.post('/api/notes', {
      data: { body, anchor: { paper_id: paperId, page: 1, bbox: chunk.bbox, quoted_text: 'overlap' } },
    })
    expect(res.ok()).toBe(true)
  }
  await page.reload()
  line = await openReader(page, paperId)

  await line.hover()
  const hoverCard = page.locator('.note-hover-card')
  await expect(hoverCard).toContainText('overlap A')
  await expect(hoverCard).toContainText('overlap B')

  await hoverCard.locator('.hover-note', { hasText: 'overlap A' }).getByRole('button', { name: 'Edit' }).click()
  await hoverCard.locator('.hover-note', { hasText: 'overlap B' }).getByRole('button', { name: 'Edit' }).click()
  await hoverCard.locator('.hover-note', { hasText: 'overlap A' }).getByRole('button', { name: 'Cancel' }).click()
  await page.waitForTimeout(50)

  // The pointer wanders off while B is still being edited: the card must stay, with B's textbox still there.
  await page.mouse.move(5, 400)
  await page.waitForTimeout(600)
  await expect(hoverCard).toBeVisible()
  await expect(hoverCard.getByRole('textbox', { name: 'Edit note' })).toHaveCount(1)
})

test('right-clicking a highlight recolours or deletes its note', async ({ page, request, paperId }) => {
  const line = await openReader(page, paperId)
  await saveNoteOn(page, line, 'menu target')
  const [note] = await (await request.get(`/api/papers/${paperId}/notes`)).json()
  const highlight = page.locator(`.highlight[data-note-id="${note.id}"]`).first()

  await line.click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Edit note' }).click()
  await expect(
    page.locator(`.note-hover-card [data-note-id="${note.id}"]`).getByRole('textbox', { name: 'Edit note' }),
  ).toBeFocused()
  await page.locator(`.note-hover-card [data-note-id="${note.id}"]`).getByRole('button', { name: 'Cancel' }).click()

  await line.click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Blue' }).click()
  await expect.poll(() => backgroundOf(highlight)).toBe('rgba(96, 165, 250, 0.4)')

  await line.click({ button: 'right' })
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('menuitem', { name: 'Delete note' }).click()
  await expect(page.locator(`article.note[data-note-id="${note.id}"]`)).toHaveCount(0)
  expect(await (await request.get(`/api/papers/${paperId}/notes`)).json()).toEqual([])
})

test('copy quote puts the quote on the clipboard', async ({ page, paperId }) => {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  const line = await openReader(page, paperId)
  await saveNoteOn(page, line, 'copy target')

  await line.click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Copy quote' }).click()

  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toContain('Highlights are the anchor')
})

test('right-clicking the pending selection highlights it in a colour straight away', async ({
  page,
  request,
  paperId,
}) => {
  const line = await openReader(page, paperId)
  await selectText(line)
  await expect(page.locator('.highlight.draft').first()).toBeVisible()

  await line.click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Highlight in Pink' }).click()

  await expect(page.getByRole('textbox', { name: 'Note' })).toHaveCount(0)
  await expect(page.locator('.highlight.draft')).toHaveCount(0)
  await expect.poll(async () => (await (await request.get(`/api/papers/${paperId}/notes`)).json()).length).toBe(1)
  const [note] = await (await request.get(`/api/papers/${paperId}/notes`)).json()
  expect([note.color, note.body]).toEqual(['#f472b6', ''])
  await expect.poll(() => backgroundOf(page.locator(`.highlight[data-note-id="${note.id}"]`).first())).toBe(
    'rgba(244, 114, 182, 0.4)',
  )
})

test('right-clicking blank page space leaves the browser menu alone', async ({ page, paperId }) => {
  await openReader(page, paperId)
  await page.evaluate(() => {
    window.addEventListener('contextmenu', (event) => {
      ;(window as unknown as { lastMenuPrevented: boolean }).lastMenuPrevented = event.defaultPrevented
    })
  })
  // The page's top margin, above the heading: on the page, inside the viewport, and not on any text.
  const box = (await page.locator('.pdf-page[data-page="1"]').boundingBox())!
  await page.mouse.click(box.x + 20, box.y + 20, { button: 'right' })

  expect(await page.evaluate(() => (window as unknown as { lastMenuPrevented: boolean }).lastMenuPrevented)).toBe(false)
  await expect(page.getByRole('menu')).toHaveCount(0)
})
