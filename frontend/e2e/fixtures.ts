import { randomUUID } from 'node:crypto'
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

/** Deletes every workspace whose name starts with `prefix`. Deleting a workspace keeps its papers and notes. */
export async function removeWorkspacesNamed(request: APIRequestContext, prefix: string) {
  const workspaces = await request.get('/api/workspaces')
  if (!workspaces.ok()) return
  for (const workspace of await workspaces.json()) {
    if (workspace.name.startsWith(prefix)) await request.delete(`/api/workspaces/${workspace.id}`)
  }
}

type Fixtures = {
  /** A freshly ingested copy of the fixture paper, removed after the test even if it fails. */
  paperId: string
  /** A unique workspace name. Every workspace whose name starts with it is deleted after the test. */
  workspaceName: string
}

export const test = base.extend<Fixtures>({
  paperId: async ({ request }, use) => {
    const id = await uploadAndWaitUntilReady(request)
    await use(id)
    await removePaperAndNotes(request, id)
  },
  workspaceName: async ({ request }, use) => {
    const name = `E2E workspace ${randomUUID().slice(0, 8)}`
    await use(name)
    await removeWorkspacesNamed(request, name)
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

/** Creates a note through the API, anchored on a line-sized rect near the top of `page`, and returns it. */
export async function addNote(request: APIRequestContext, paperId: string, page: number, body: string) {
  const created = await request.post('/api/notes', {
    data: { body, anchor: { paper_id: paperId, page, bbox: [[72, 110, 540, 124]], quoted_text: `Quote for ${body}` } },
  })
  expect(created.status()).toBe(201)
  return (await created.json()) as { id: string }
}

/** Largest offset in px between two elements' boxes; retried by callers while layout settles. */
export async function boxOffset(a: Locator, b: Locator): Promise<number> {
  const [boxA, boxB] = [await a.boundingBox(), await b.boundingBox()]
  if (!boxA || !boxB) return Number.POSITIVE_INFINITY
  return Math.max(Math.abs(boxA.x - boxB.x), Math.abs(boxA.y - boxB.y), Math.abs(boxA.width - boxB.width))
}
