import { fileURLToPath } from 'node:url'
import type { Page } from '@playwright/test'
import { dragBox, expect, openReader, removePaperAndNotes, test, uploadAndWaitUntilReady } from './fixtures'

// citation-paper.pdf (fixtures/make_citation_paper.py): page 2 has "Figure 1: A figure caption." at (316, 400).
const CITATION_FILE = fileURLToPath(new URL('./fixtures/citation-paper.pdf', import.meta.url))
const CAPTION = 'Figure 1: A figure caption.'
const FIGURE_BOX: [number, number, number, number] = [250, 300, 480, 395]

/** Notes tab → New note on this paper, with the Kind picked by its label. */
async function startPaperNote(page: Page, kindLabel: string) {
  await page.getByRole('button', { name: 'New note on this paper' }).click()
  await page.getByRole('combobox', { name: 'Kind' }).last().click()
  await page.getByRole('option', { name: kindLabel, exact: true }).click()
}

test('Five Cs fills in its five headings, and the Kind filter then shows only the summary', async ({ page, request, paperId }) => {
  await openReader(page, paperId)
  await startPaperNote(page, 'Summary')
  await page.getByRole('textbox', { name: 'New note' }).fill('A short summary of the paper.')
  await page.getByRole('button', { name: 'Save note' }).click()
  await expect(page.locator('article.note', { hasText: 'A short summary' })).toBeVisible()

  await startPaperNote(page, 'Five Cs')
  const body = page.getByRole('textbox', { name: 'New note' })
  const fiveCs = (await body.inputValue()).split('\n')
  expect(fiveCs).toHaveLength(5)
  for (const line of fiveCs) expect(line).toMatch(/^\w[\w ]*:$/)
  await body.fill(`${fiveCs[0]} a survey`)
  await page.getByRole('button', { name: 'Save note' }).click()
  await expect(page.locator('article.note')).toHaveCount(2)

  await page.getByRole('combobox', { name: 'Kind' }).first().click()
  await page.getByRole('option', { name: 'Summary', exact: true }).click()
  const cards = page.locator('article.note')
  await expect(cards).toHaveCount(1)
  await expect(cards.first()).toContainText('A short summary')
  expect((await (await request.get(`/api/papers/${paperId}/notes`)).json()).map((n: { kind: string }) => n.kind).sort()).toEqual(['five_cs', 'summary'])
})

test('a Summary written with New note on this paper comes back with its kind after a reload', async ({ page, paperId }) => {
  await openReader(page, paperId)
  await startPaperNote(page, 'Summary')
  await page.getByRole('textbox', { name: 'New note' }).fill('Kept across a reload.')
  await page.getByRole('button', { name: 'Save note' }).click()
  await expect(page.locator('article.note', { hasText: 'Kept across a reload.' })).toBeVisible()

  await page.reload()
  const card = page.locator('article.note', { hasText: 'Kept across a reload.' })
  await expect(card).toBeVisible()
  await expect(card.locator('.note-kind')).toHaveText('Summary')
})

test('a figure note survives a reload as an unfilled outline, with the caption as its quote, and Capture table still works', async ({ page, request }) => {
  const id = await uploadAndWaitUntilReady(request, CITATION_FILE, 'citation-paper.pdf')
  try {
    await openReader(page, id, 'Fixtures cite fixtures')
    const toggle = page.getByRole('button', { name: 'Note on figure' })
    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-pressed', 'true')
    await page.locator('.pdf-page[data-page="2"]').scrollIntoViewIfNeeded()
    await dragBox(page, 2, FIGURE_BOX)

    await expect(page.getByText('Figure on p. 2')).toBeVisible()
    const questions = page.getByRole('textbox', { name: 'Note' })
    await expect(questions).toHaveValue(/Are the axes labelled\?[\s\S]*error bar[\s\S]*conclusions follow/)
    await page.getByRole('button', { name: 'Save note' }).click()
    await expect(page.locator('article.note')).toHaveCount(1)

    const [note] = await (await request.get(`/api/papers/${id}/notes`)).json()
    expect(note.kind).toBe('figure')
    expect(note.anchors[0].page).toBe(2)
    expect(note.anchors[0].quoted_text).toBe(CAPTION)

    await page.reload()
    const figure = page.locator('.pdf-page[data-page="2"] .highlight.figure')
    await expect(figure).toHaveCount(1)
    expect(await figure.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe('rgba(0, 0, 0, 0)')
    const [pageBox, rect] = [await page.locator('.pdf-page[data-page="2"]').boundingBox(), await figure.boundingBox()]
    const scale = pageBox!.width / 612
    expect(rect!.x - pageBox!.x).toBeCloseTo(FIGURE_BOX[0] * scale, -1)
    expect(rect!.y - pageBox!.y).toBeCloseTo(FIGURE_BOX[1] * scale, -1)

    const capture = page.getByRole('button', { name: 'Capture table' })
    await capture.click()
    await expect(capture).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('section.cursor-crosshair')).toHaveCount(1)
    await page.keyboard.press('Escape')
    await expect(capture).toHaveAttribute('aria-pressed', 'false')
  } finally {
    await removePaperAndNotes(request, id)
  }
})
