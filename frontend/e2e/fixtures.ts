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
  // Notes and datasets deliberately survive paper deletion, so remove them first.
  for (const note of await notes.json()) await request.delete(`/api/notes/${note.id}`)
  const datasets = await request.get(`/api/datasets?paper_id=${paperId}`)
  for (const dataset of datasets.ok() ? await datasets.json() : []) {
    await request.delete(`/api/datasets/${dataset.id}?force=true`)
  }
  await request.delete(`/api/papers/${paperId}`)
}

/** A captured table on `page` of the paper, as the capture dialog saves one: every cell read from that page. */
export async function addTable(request: APIRequestContext, paperId: string, page: number, name: string, rows: string[][]) {
  const region: Rect = [72, 110, 540, 110 + 14 * rows.length]
  const grid = {
    columns: rows[0].map((header) => ({ name: header })),
    rows: rows.slice(1).map((row, r) => ({
      cells: row.map((raw, c) => ({ raw, extracted: raw, page, bbox: [[72 + 150 * c, 124 + 14 * r, 150 + 150 * c, 134 + 14 * r]] })),
    })),
  }
  const created = await request.post('/api/datasets', { data: { name, kind: 'table', paper_id: paperId, page, region, grid } })
  expect(created.status()).toBe(201)
  return (await created.json()) as { id: string; region: Rect; columns: { id: string; name: string }[] }
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
  /** Another, separately ingested copy: workspace specs need two papers. */
  secondPaperId: string
  /** A unique workspace name. Every workspace whose name starts with it is deleted after the test. */
  workspaceName: string
  /** An empty workspace named `workspaceName`. */
  workspaceId: string
}

export const test = base.extend<Fixtures>({
  paperId: async ({ request }, use) => {
    const id = await uploadAndWaitUntilReady(request)
    await use(id)
    await removePaperAndNotes(request, id)
  },
  secondPaperId: async ({ request }, use) => {
    const id = await uploadAndWaitUntilReady(request)
    await use(id)
    await removePaperAndNotes(request, id)
  },
  workspaceName: async ({ request }, use) => {
    const name = `E2E workspace ${randomUUID().slice(0, 8)}`
    await use(name)
    await removeWorkspacesNamed(request, name)
  },
  // No teardown of its own: `workspaceName` deletes it.
  workspaceId: async ({ request, workspaceName }, use) => {
    const created = await request.post('/api/workspaces', { data: { name: workspaceName } })
    expect(created.status()).toBe(201)
    await use((await created.json()).id)
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

/**
 * Asks with Enter, and waits until the answer is saved: only a saved answer has `data-output-id`.
 * `timeoutMs` defaults to 15s; pass a longer one for the suite's first retrieving question, which also pays
 * for loading the embedding model on a freshly recreated API.
 */
export async function ask(page: Page, question: string, timeoutMs = 15_000): Promise<Locator> {
  await page.getByRole('textbox', { name: 'Question' }).fill(question)
  await page.getByRole('textbox', { name: 'Question' }).press('Enter')
  const answer = page.locator('article.chat-answer[data-output-id]', { hasText: question })
  await expect(answer.locator('.chat-answer-footer')).toContainText('AI · ', { timeout: timeoutMs })
  return answer
}

/** Selects all of an element's text like a mouse drag, then releases the mouse. */
export async function selectAllOf(element: Locator) {
  await element.evaluate((node) => {
    const range = document.createRange()
    range.selectNodeContents(node)
    window.getSelection()!.removeAllRanges()
    window.getSelection()!.addRange(range)
  })
  await element.dispatchEvent('mouseup')
}

/** Largest offset in px between two elements' boxes; retried by callers while layout settles. */
export async function boxOffset(a: Locator, b: Locator): Promise<number> {
  const [boxA, boxB] = [await a.boundingBox(), await b.boundingBox()]
  if (!boxA || !boxB) return Number.POSITIVE_INFINITY
  return Math.max(Math.abs(boxA.x - boxB.x), Math.abs(boxA.y - boxB.y), Math.abs(boxA.width - boxB.width))
}
