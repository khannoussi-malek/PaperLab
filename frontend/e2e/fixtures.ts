import { randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { test as base, expect, type APIRequestContext, type Locator, type Page } from '@playwright/test'
import { E2E_CONNECTION_PREFIX } from './globalSetup'

export { expect }

export const FIXTURE_FILE = fileURLToPath(new URL('./fixtures/sample-paper.pdf', import.meta.url))
export const FIXTURE_TITLE = 'PaperLab E2E Fixture'
export const FIRST_LINE = 'Highlights are the anchor'
export const TABLE_FIXTURE_FILE = fileURLToPath(new URL('./fixtures/table-paper.pdf', import.meta.url))
/** The start of the table paper's sentence line, which holds "88.5 ± 0.3 F1". */
export const TABLE_LINE = 'Our best model reaches'
/** Twelve pages, about 30,000 characters: too long for chat to send whole, so asking it needs the search model. */
export const LONG_FIXTURE_FILE = fileURLToPath(new URL('./fixtures/long-paper.pdf', import.meta.url))
export type Rect = [number, number, number, number]

export async function uploadAndWaitUntilReady(
  request: APIRequestContext,
  file = FIXTURE_FILE,
  filename = 'sample-paper.pdf',
): Promise<string> {
  const upload = await request.post('/api/papers', {
    multipart: { file: { name: filename, mimeType: 'application/pdf', buffer: await readFile(file) } },
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

/** Deletes every chart whose title starts with `prefix`, then every dataset whose name does (even if charts use it). */
export async function removeChartsAndDataNamed(request: APIRequestContext, prefix: string) {
  const charts = await request.get('/api/charts')
  for (const chart of charts.ok() ? await charts.json() : []) {
    if (chart.title.startsWith(prefix)) await request.delete(`/api/charts/${chart.id}`)
  }
  const datasets = await request.get('/api/datasets')
  for (const dataset of datasets.ok() ? await datasets.json() : []) {
    if (dataset.name.startsWith(prefix)) await request.delete(`/api/datasets/${dataset.id}?force=true`)
  }
}

type SavedDataset = { id: string; columns: { id: string; name: string }[] }

/** A bar chart spec: each named y column of `dataset` against its x column. */
export function barSpec(dataset: SavedDataset, x: string | null, ys: string[]) {
  const column = (name: string) => {
    const found = dataset.columns.find((c) => c.name === name)
    if (!found) throw new Error(`no column ${name}`)
    return found.id
  }
  return {
    version: 1,
    type: 'bar',
    series: ys.map((y, i) => ({
      id: `s${i + 1}`,
      name: '',
      dataset_id: dataset.id,
      x: x === null ? null : column(x),
      y: column(y),
      error: 'none',
      trend: 'none',
      multiply: 1,
    })),
  }
}

/** Imports `csv` as your own data through the API and returns the dataset. */
export async function addOwnData(request: APIRequestContext, name: string, csv: string) {
  const created = await request.post('/api/datasets/import', {
    multipart: { name, file: { name: 'data.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) } },
  })
  expect(created.status()).toBe(201)
  return (await created.json()) as { id: string; columns: { id: string; name: string }[] }
}

/** Creates a chart through the API and returns it. */
export async function addChart(request: APIRequestContext, title: string, spec: object) {
  const created = await request.post('/api/charts', { data: { title, spec } })
  expect(created.status()).toBe(201)
  return (await created.json()) as { id: string; title: string }
}

/**
 * Clicks the `index`th bar of the chart on the page. Plotly's drag layer lies over the bars, so the click goes to the
 * bar's position rather than its element; just above the bar's base, which is on the chart for linear axes.
 */
export async function clickBar(page: Page, index: number) {
  const box = await page.locator('.chart-view .barlayer .point path').nth(index).boundingBox()
  if (!box) throw new Error(`bar ${index} is not drawn`)
  await page.mouse.click(box.x + box.width / 2, box.y + box.height - 4)
}

/** The chat dropdown's remembered pick (`features/chat/chatModel.ts`). */
export const CHAT_MODEL_KEY = 'paperlab-chat-model'
/** The one key `LLM_PROVIDER=fake` rejects when a connection is tested. */
export const FAKE_BAD_KEY = 'bad-key'

export type LlmConnection = { id: string; label: string; modelId: string; modelName: string }

/** A connection on the fake stack (no network), with one model listed in chat. OpenAI-compatible unless `fields` say. */
export async function addLlmConnection(
  request: APIRequestContext,
  label: string,
  modelName = 'e2e-model',
  fields: Record<string, unknown> = {},
): Promise<LlmConnection> {
  const created = await request.post('/api/llm/connections', {
    data: { kind: 'openai_compatible', label, base_url: 'http://fake-provider.test/v1', ...fields },
  })
  expect(created.status()).toBe(201)
  const { id } = await created.json()
  const model = await request.post(`/api/llm/connections/${id}/models`, { data: { name: modelName } })
  expect(model.status()).toBe(201)
  return { id, label, modelId: (await model.json()).id, modelName }
}

/** The id of the model chat uses when none is picked, or null. */
export async function defaultModelId(request: APIRequestContext): Promise<string | null> {
  const listed = await request.get('/api/llm/models')
  expect(listed.status(), 'the owner’s default model has to be readable before a test moves it').toBe(200)
  const models: { id: string; is_default: boolean }[] = await listed.json()
  return models.find((model) => model.is_default)?.id ?? null
}

/** Deletes every connection whose label starts with `prefix`, with its models. A refused delete fails the test. */
export async function removeConnectionsNamed(request: APIRequestContext, prefix: string) {
  const connections = await request.get('/api/llm/connections')
  expect(connections.status(), 'the test’s connections have to be listable to be cleaned up').toBe(200)
  for (const connection of await connections.json()) {
    if (!connection.label.startsWith(prefix)) continue
    const deleted = await request.delete(`/api/llm/connections/${connection.id}`)
    expect(deleted.status(), `left "${connection.label}" behind on the owner's database`).toBe(204)
  }
}

/** Starts the chat dropdown on `modelId`, as a remembered pick would, on every page load of this test. */
export async function pickChatModel(page: Page, modelId: string) {
  await page.addInitScript(([key, id]) => window.localStorage.setItem(key, id), [CHAT_MODEL_KEY, modelId] as const)
}

type Fixtures = {
  /** A freshly ingested copy of the fixture paper, removed after the test even if it fails. */
  paperId: string
  /** Another, separately ingested copy: workspace specs need two papers. */
  secondPaperId: string
  /** A freshly ingested copy of the table paper: a captioned 3 × 3 table and "88.5 ± 0.3 F1" on page 1. */
  tablePaperId: string
  /** A freshly ingested copy of the long paper, which chat can't send whole. */
  longPaperId: string
  /** A unique workspace name. Every workspace whose name starts with it is deleted after the test. */
  workspaceName: string
  /** An empty workspace named `workspaceName`. */
  workspaceId: string
  /** A unique prefix for chart titles and dataset names. Every chart and dataset starting with it is deleted after the test. */
  dataName: string
  /**
   * A unique prefix for connection labels. After the test the owner's default model is put back if the test moved it,
   * and then every connection starting with it is deleted: E2E runs on the owner's database.
   */
  llmName: string
  /** A connection named `llmName` with one model, `e2e-model`. */
  llmConnection: LlmConnection
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
  tablePaperId: async ({ request }, use) => {
    const id = await uploadAndWaitUntilReady(request, TABLE_FIXTURE_FILE, 'table-paper.pdf')
    await use(id)
    await removePaperAndNotes(request, id)
  },
  longPaperId: async ({ request }, use) => {
    const id = await uploadAndWaitUntilReady(request, LONG_FIXTURE_FILE, 'long-paper.pdf')
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
  dataName: async ({ request }, use) => {
    const name = `E2E data ${randomUUID().slice(0, 8)}`
    await use(name)
    await removeChartsAndDataNamed(request, name)
  },
  llmName: async ({ request }, use) => {
    const name = `${E2E_CONNECTION_PREFIX}${randomUUID().slice(0, 8)}`
    const ownersDefault = await defaultModelId(request)
    await use(name)
    // Unconditional: a "restore only if it looks different" check can read a stale value (the test's own change
    // still in flight, or a slow request under load) and wrongly skip the restore. Always put it back; a no-op PUT
    // when nothing moved is harmless. A null ownersDefault means the owner had no default to restore.
    const restored = ownersDefault === null ? null : await request.put('/api/llm/default', { data: { model_id: ownersDefault } })
    // Sweep before checking the restore, so the connections go even when the restore failed -- and then say so.
    await removeConnectionsNamed(request, name)
    if (restored !== null) expect(restored.status(), `could not put the owner's default model (${ownersDefault}) back`).toBe(200)
  },
  // No teardown of its own: `llmName` deletes it.
  llmConnection: async ({ request, llmName }, use) => {
    await use(await addLlmConnection(request, llmName))
  },
})

/** Opens the reader and returns page 1's text-layer line holding `firstLine` once it is rendered. */
export async function openReader(page: Page, paperId: string, firstLine = FIRST_LINE): Promise<Locator> {
  await page.goto(`/#/papers/${paperId}`)
  const line = page.locator('.pdf-page[data-page="1"] .textLayer span', { hasText: firstLine })
  await expect(line).toBeVisible()
  return line
}

/** Drags a box over `region` (PDF points, top-left origin) on a page, at whatever zoom the reader shows. */
export async function dragBox(page: Page, pageNumber: number, [x0, y0, x1, y1]: Rect) {
  const box = await page.locator(`.pdf-page[data-page="${pageNumber}"]`).boundingBox()
  if (!box) throw new Error(`page ${pageNumber} is not rendered`)
  const scale = box.width / 612 // the fixtures are US Letter
  await page.mouse.move(box.x + x0 * scale, box.y + y0 * scale)
  await page.mouse.down()
  await page.mouse.move(box.x + x1 * scale, box.y + y1 * scale, { steps: 8 })
  await page.mouse.up()
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

/** Selects `text` inside a text-layer span, like a mouse drag over just those characters, then releases the mouse. */
export async function selectSubstring(span: Locator, text: string) {
  await span.evaluate((element, wanted) => {
    const node = element.firstChild!
    const start = node.textContent!.indexOf(wanted)
    if (start < 0) throw new Error(`"${wanted}" is not in "${node.textContent}"`)
    const range = document.createRange()
    range.setStart(node, start)
    range.setEnd(node, start + wanted.length)
    window.getSelection()!.removeAllRanges()
    window.getSelection()!.addRange(range)
  }, text)
  await span.dispatchEvent('mouseup')
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
