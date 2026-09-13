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
