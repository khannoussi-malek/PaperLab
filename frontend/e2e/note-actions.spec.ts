import { backgroundOf } from './computedStyle'
import { expect, openReader, saveNoteOn, test } from './fixtures'

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
