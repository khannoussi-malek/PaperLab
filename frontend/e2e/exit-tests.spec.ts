import { fileURLToPath } from 'node:url'
import type { Page } from '@playwright/test'
import {
  addLlmConnection,
  ask,
  dragBox,
  expect,
  openReader,
  pickChatModel,
  removePaperAndNotes,
  selectAllOf,
  test,
  uploadAndWaitUntilReady,
} from './fixtures'

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

// Part B: the check. The fake model's reply parses to 3 kept lines and 1 dropped one (the dropped line is a rewrite).
const REWRITE = 'Here is a better summary you could use.'

/** A model that counts as local (no confirmation), picked in chat. `llmName` cleans it up after the test. */
async function useLocalModel(page: Page, request: Parameters<typeof addLlmConnection>[0], llmName: string) {
  const local = await addLlmConnection(request, `${llmName} local`, 'e2e-local', { base_url: 'http://localhost:11434/v1' })
  await pickChatModel(page, local.modelId)
}

/** Saves a note of this kind with this body on the paper and returns its card. */
async function writeNote(page: Page, kindLabel: string, body: string) {
  await startPaperNote(page, kindLabel)
  await page.getByRole('textbox', { name: 'New note' }).fill(body)
  await page.getByRole('button', { name: 'Save note' }).click()
  const card = page.locator('article.note', { hasText: body })
  await expect(card).toBeVisible()
  return card
}

test('write and check a summary: lines cite the paper, and the model writes nothing to keep', async ({ page, request, paperId, llmName }) => {
  await useLocalModel(page, request, llmName)
  await openReader(page, paperId)
  const card = await writeNote(page, 'Summary', 'It anchors every note on a passage.')
  await expect(card.locator('.note-kind')).toHaveText('Summary')
  await expect(card).toContainText('You')

  await card.getByRole('button', { name: 'Check against the paper' }).click()
  const result = card.locator('.check-result')
  await expect(result.locator('.check-line[data-verdict="missing"]').first()).toBeVisible()
  await expect(result.locator('.check-line[data-verdict="unsupported"]').first()).toBeVisible()
  await expect(result.locator('.check-dropped')).toContainText("1 line of the reply didn't follow")
  await expect(page.getByText(REWRITE)).toHaveCount(0)

  await result.locator('.check-line[data-verdict="missing"] .check-cite').first().click()
  await expect(page.locator('.pdf-page .chunk-flash').first()).toBeInViewport()
  await expect(card).toContainText('You')

  await selectAllOf(result)
  await expect(page.getByRole('button', { name: 'Save as note' })).toHaveCount(0)
  await expect(page.getByText(REWRITE)).toHaveCount(0)
})

test('editing a checked summary marks the check out of date, and checking again clears it', async ({ page, request, paperId, llmName }) => {
  await useLocalModel(page, request, llmName)
  await openReader(page, paperId)
  const written = await writeNote(page, 'Summary', 'A first version of the summary.')
  const card = page.locator(`article.note[data-note-id="${await written.getAttribute('data-note-id')}"]`) // its text changes below
  await card.getByRole('button', { name: 'Check against the paper' }).click()
  await expect(card.locator('.check-line').first()).toBeVisible()
  await expect(card.locator('.check-stale')).toHaveCount(0)

  await card.getByRole('button', { name: 'Edit', exact: true }).click()
  await card.getByRole('textbox', { name: 'Edit note' }).fill('A second version of the summary.')
  await card.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(card.locator('.check-stale')).toContainText('Out of date')

  await card.getByRole('button', { name: 'Check again' }).click()
  await expect(card.locator('.check-stale')).toHaveCount(0)
  await expect(card.locator('.check-line').first()).toBeVisible()
})

test('an AI note cannot be checked, even after it is given a checkable kind', async ({ page, request, paperId, llmName }) => {
  await useLocalModel(page, request, llmName)
  await page.goto(`/#/papers/${paperId}?tab=chat`)
  const answer = await ask(page, 'Create notes to help me understand this paper')
  await answer.locator('.suggested-note').first().getByRole('button', { name: 'Save', exact: true }).click()
  await expect(answer.locator('.suggested-note').first()).toContainText('Saved')

  await page.goto(`/#/papers/${paperId}?tab=notes`)
  const card = page.locator('article.note', { hasText: 'The method anchors every note on a passage' })
  await card.getByRole('button', { name: 'Edit', exact: true }).click()
  await card.getByRole('combobox', { name: 'Kind' }).click()
  await page.getByRole('option', { name: 'Five Cs', exact: true }).click()
  await card.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(card.locator('.note-kind')).toHaveText('Five Cs')

  await expect(card.getByRole('button', { name: 'Check against the paper' })).toBeDisabled()
  await card.locator('span[tabindex="0"]').focus()
  await expect(page.getByRole('tooltip').first()).toContainText('Only text you wrote can be checked. This note came from AI.')
})

test('the Reading control shows pass 1’s test, opens the composer, and reports the check', async ({ page, request, paperId, llmName }) => {
  await useLocalModel(page, request, llmName)
  await openReader(page, paperId)
  await page.getByRole('button', { name: 'Reading' }).click()
  await expect(page.getByText('Your five Cs: not written yet')).toBeVisible()
  await page.getByRole('button', { name: 'Write it' }).click()

  const body = page.getByRole('textbox', { name: 'New note' })
  const headings = (await body.inputValue()).split('\n')
  expect(headings).toHaveLength(5)
  await body.fill(headings.map((heading) => `${heading} something I wrote`).join('\n'))
  await page.getByRole('button', { name: 'Save note' }).click()
  const card = page.locator('article.note', { hasText: 'something I wrote' })
  await expect(card.locator('.note-kind')).toHaveText('Five Cs')
  await card.getByRole('button', { name: 'Check against the paper' }).click()
  await expect(card.locator('.check-line').first()).toBeVisible()
  await expect(card.getByRole('button', { name: 'Check again' })).toBeEnabled()

  await page.getByRole('button', { name: 'Reading' }).click()
  await expect(page.getByText(/Your five Cs: checked .*: 1 missing, 1 unsupported/)).toBeVisible()
})

test('a cloud model asks first: the dialog names the host, Cancel sends nothing, Send shows the lines', async ({ page, paperId, llmConnection }) => {
  await pickChatModel(page, llmConnection.modelId) // fake-provider.test is not local
  await openReader(page, paperId)
  const card = await writeNote(page, 'Summary', 'A summary for a cloud model.')
  await card.getByRole('button', { name: 'Check against the paper' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('fake-provider.test')
  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(dialog).toHaveCount(0)
  await expect(card.locator('.check-line')).toHaveCount(0)
  expect(await (await page.request.get(`/api/papers/${paperId}/checks`)).json()).toEqual([])

  await card.getByRole('button', { name: 'Check against the paper' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Send' }).click()
  await expect(card.locator('.check-line').first()).toBeVisible()
})
