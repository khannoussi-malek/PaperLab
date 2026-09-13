import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { test as base, expect, type APIRequestContext, type Locator, type Page } from '@playwright/test'

export { expect }

export const FIXTURE_FILE = fileURLToPath(new URL('./fixtures/sample-paper.pdf', import.meta.url))
export const FIXTURE_TITLE = 'PaperLab E2E Fixture'
export const FIRST_LINE = 'Highlights are the anchor'
export type Rect = [number, number, number, number]

export async function uploadAndWaitUntilReady(request: APIRequestContext): Promise<string> {
  const upload = await request.post('/api/papers', {
    multipart: {
      file: { name: 'sample-paper.pdf', mimeType: 'application/pdf', buffer: await readFile(FIXTURE_FILE) },
    },
  })
  expect(upload.status()).toBe(201)
  const { id } = await upload.json()
  await expect
    .poll(async () => (await (await request.get(`/api/papers/${id}`)).json()).status, { timeout: 30_000 })
    .toBe('ready')
  return id
}

export async function removePaperAndNotes(request: APIRequestContext, paperId: string) {
  const notes = await request.get(`/api/papers/${paperId}/notes`)
  if (!notes.ok()) return // already deleted
  // Notes deliberately survive paper deletion, so remove them first.
  for (const note of await notes.json()) await request.delete(`/api/notes/${note.id}`)
  await request.delete(`/api/papers/${paperId}`)
}

/** `paperId`: a freshly ingested copy of the fixture paper, removed after the test even if it fails. */
export const test = base.extend<{ paperId: string }>({
  paperId: async ({ request }, use) => {
    const id = await uploadAndWaitUntilReady(request)
    await use(id)
    await removePaperAndNotes(request, id)
  },
})

/** Opens the reader and returns page 1's first text-layer line once it is rendered. */
export async function openReader(page: Page, paperId: string): Promise<Locator> {
  await page.goto(`/#/papers/${paperId}`)
  const line = page.locator('.pdf-page[data-page="1"] .textLayer span', { hasText: FIRST_LINE })
  await expect(line).toBeVisible()
  return line
}

/** Selects from the start of `start` to the end of `end` like a mouse drag, then releases the mouse. */
export async function selectText(start: Locator, end: Locator = start) {
  const endElement = await end.elementHandle()
  await start.evaluate((from, to) => {
    const range = document.createRange()
    range.setStart(from.firstChild!, 0)
    range.setEnd(to!.firstChild!, to!.textContent!.length)
    window.getSelection()!.removeAllRanges()
    window.getSelection()!.addRange(range)
  }, endElement)
  await start.dispatchEvent('mouseup')
}

export async function saveNoteOn(page: Page, line: Locator, body: string): Promise<Locator> {
  await selectText(line)
  await page.getByRole('textbox', { name: 'Note' }).fill(body)
  await page.getByRole('button', { name: 'Save note' }).click()
  const card = page.locator('article.note', { hasText: body })
  await expect(card).toBeVisible()
  return card
}

/** Largest offset in px between two elements' boxes; retried by callers while layout settles. */
export async function boxOffset(a: Locator, b: Locator): Promise<number> {
  const [boxA, boxB] = [await a.boundingBox(), await b.boundingBox()]
  if (!boxA || !boxB) return Number.POSITIVE_INFINITY
  return Math.max(Math.abs(boxA.x - boxB.x), Math.abs(boxA.y - boxB.y), Math.abs(boxA.width - boxB.width))
}
