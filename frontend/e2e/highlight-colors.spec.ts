import { backgroundOf } from './computedStyle'
import { expect, openReader, saveNoteOn, selectText, test } from './fixtures'

test('a note saved in Green is drawn green, and the next selection starts on Green', async ({
  page,
  request,
  paperId,
}) => {
  const line = await openReader(page, paperId)
  await selectText(line)
  const composer = page.locator('form', { has: page.getByRole('textbox', { name: 'Note' }) })
  await composer.getByRole('button', { name: 'Green' }).click()
  await expect(composer.getByRole('button', { name: 'Green' })).toHaveAttribute('aria-pressed', 'true')
  await composer.getByRole('textbox', { name: 'Note' }).fill('green claim')
  await composer.getByRole('button', { name: 'Save note' }).click()

  await expect(page.locator('article.note', { hasText: 'green claim' })).toBeVisible()
  const [note] = await (await request.get(`/api/papers/${paperId}/notes`)).json()
  expect(note.color).toBe('#4ade80')
  const highlight = page.locator(`.highlight[data-note-id="${note.id}"]`).first()
  await expect.poll(() => backgroundOf(highlight)).toBe('rgba(74, 222, 128, 0.4)')

  await page.reload()
  const secondPageLine = page.locator('.pdf-page[data-page="2"] .textLayer span', { hasText: 'The second page' })
  await secondPageLine.scrollIntoViewIfNeeded()
  await selectText(secondPageLine)
  await expect(composer.getByRole('button', { name: 'Green' })).toHaveAttribute('aria-pressed', 'true')
})

test('recolouring a note from the notes panel, including a custom colour, persists', async ({ page, paperId }) => {
  const line = await openReader(page, paperId)
  const card = await saveNoteOn(page, line, 'recolour me')
  const highlight = page.locator('.highlight:not(.draft)').first()
  await expect.poll(() => backgroundOf(highlight)).toBe('rgba(250, 204, 21, 0.4)')

  await card.getByRole('button', { name: 'Blue' }).click()
  await expect.poll(() => backgroundOf(highlight)).toBe('rgba(96, 165, 250, 0.4)')

  await card.getByLabel('Custom colour').fill('#ff00aa')
  await expect.poll(() => backgroundOf(highlight)).toBe('rgba(255, 0, 170, 0.4)')
  await expect(card.getByRole('button', { name: 'Blue' })).toHaveAttribute('aria-pressed', 'false')

  await page.reload()
  await expect.poll(() => backgroundOf(page.locator('.highlight:not(.draft)').first())).toBe('rgba(255, 0, 170, 0.4)')
})

test("an AI note's highlight is drawn fainter than the reader's own, in the same colour", async ({ page, paperId }) => {
  // AI notes only come from chat or MCP, so the list is faked: one of each provenance, all green.
  const note = (id: string, provenance: string) => ({
    id: `00000000-0000-4000-8000-00000000040${id}`,
    body: `note ${id}`,
    provenance,
    color: '#4ade80',
    source_id: null,
    created_at: '2026-09-14T00:00:00Z',
    updated_at: '2026-09-14T00:00:00Z',
    anchors: [{ paper_id: paperId, page: 1, bbox: [[72, 100 + Number(id) * 30, 300, 115 + Number(id) * 30]], quoted_text: `quote ${id}` }],
  })
  const notes = [note('1', 'human'), note('2', 'llm'), note('3', 'llm_edited')]
  await page.route('**/api/papers/*/notes', (route) =>
    route.request().method() === 'GET' ? route.fulfill({ json: notes }) : route.fallback(),
  )
  await openReader(page, paperId)

  const highlight = (id: string) => page.locator(`.highlight[data-note-id="${note(id, '').id}"]`)
  await expect.poll(() => backgroundOf(highlight('1'))).toBe('rgba(74, 222, 128, 0.4)')
  await expect.poll(() => backgroundOf(highlight('2'))).toBe('rgba(74, 222, 128, 0.15)')
  await expect.poll(() => backgroundOf(highlight('3'))).toBe('rgba(74, 222, 128, 0.15)')
})
