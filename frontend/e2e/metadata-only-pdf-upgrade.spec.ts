import type { APIRequestContext, Page } from '@playwright/test'
import { expect, FIXTURE_FILE, removePaperAndNotes, test } from './fixtures'
import { FREE_SOURCES_ON, MOVES_PAPER_SOURCES, readSourceSettings, setSourceSettings, type SourceSettings } from './paperSources'

// A paper saved without a PDF gets its PDF later (PR 2): it keeps its id, tags, notes and workspaces, and a search hit
// awaiting it moves from "Saved without a PDF" / "Not retrieved" to assessable. API runs with DISCOVERY_PROVIDER=fake.
const LANDING = 'PaperLab Landing Page Fixture'
const FAKE_DOI_PREFIX = '10.5555/paperlab-e2e-'
const HIT_TITLE = 'paperlab pagination fixture 2' // no free PDF, a search_page() fixture (as workspace-snowball-prisma)
const HIT_DOI = `${FAKE_DOI_PREFIX}page-2`
const tag = MOVES_PAPER_SOURCES // these turn paper sources on, so they run one at a time after the parallel specs

test.describe.configure({ mode: 'serial' })

async function removeLeftovers(request: APIRequestContext) {
  const papers = await request.get('/api/papers')
  for (const paper of papers.ok() ? ((await papers.json()) as { id: string; doi: string | null }[]) : []) {
    if (paper.doi?.startsWith(FAKE_DOI_PREFIX)) await removePaperAndNotes(request, paper.id)
  }
}

let owners: SourceSettings

test.beforeEach(async ({ request }) => {
  await removeLeftovers(request)
  owners = await readSourceSettings(request)
  await setSourceSettings(request, { enabled: FREE_SOURCES_ON })
})

test.afterEach(async ({ request }) => {
  await removeLeftovers(request)
  await setSourceSettings(request, owners)
})

/** Finds the Landing Page paper, Adds it (refused: no free PDF), then retries with Save without PDF. Returns its id. */
async function saveLandingWithoutPdf(page: Page): Promise<string> {
  await page.goto('/')
  await page.getByRole('button', { name: 'Find papers' }).click()
  const dialog = page.getByRole('dialog', { name: 'Find papers' })
  await dialog.getByRole('textbox', { name: 'Title, DOI, arXiv ID or OpenAlex ID' }).fill('fixture')
  await dialog.getByRole('button', { name: 'Search' }).click()
  const row = dialog.locator('.candidate-row').filter({ hasText: LANDING })
  await row.getByRole('button', { name: 'Add' }).click()
  await expect(row.getByRole('alert')).toContainText('No free PDF was found for this paper.')
  await row.getByRole('button', { name: 'Save without PDF' }).click()
  const inLibrary = row.getByRole('link', { name: 'In library' })
  await expect(inLibrary).toBeVisible()
  const id = (await inLibrary.getAttribute('href'))!.replace('#/papers/', '')
  await page.keyboard.press('Escape')
  return id
}


test('uploading the PDF keeps the paper, its tag, workspace and note', { tag }, async ({ page, request, workspaceId }) => {
  const id = await saveLandingWithoutPdf(page)
  expect((await request.put(`/api/workspaces/${workspaceId}/papers/${id}`)).status()).toBe(204)
  const tagged = await request.post(`/api/workspaces/${workspaceId}/tags/apply`, { data: { tag: 'upgrade-keeps', paper_ids: [id] } })
  expect(tagged.ok()).toBe(true)
  const note = await request.post('/api/notes', { data: { body: 'E2E upgrade note', paper_id: id } })
  expect(note.status()).toBe(201)
  const noteId = ((await note.json()) as { id: string }).id

  await page.goto(`/#/papers/${id}`)
  const details = page.getByRole('region', { name: 'Paper details' })
  await expect(details.getByText('No PDF yet')).toBeVisible()
  await details.getByLabel(`Upload PDF for ${LANDING}`).setInputFiles(FIXTURE_FILE)

  await expect(page.locator('.pdf-page[data-page="1"]')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('No PDF yet')).toHaveCount(0)
  expect(page.url()).toContain(`#/papers/${id}`)

  const tags = (await (await request.get(`/api/papers/${id}/tags`)).json()) as { workspace_id: string; tags: string[] }[]
  expect(tags.find((group) => group.workspace_id === workspaceId)?.tags).toContain('upgrade-keeps')
  const members = (await (await request.get(`/api/workspaces/${workspaceId}/papers`)).json()) as { id: string }[]
  expect(members.map((paper) => paper.id)).toContain(id)
  const notes = (await (await request.get(`/api/papers/${id}/notes`)).json()) as { id: string }[]
  expect(notes.map((n) => n.id)).toContain(noteId)
})

test('a hit whose paper has no PDF waits in step 2, is blocked in step 3 and not retrieved, until the upload', { tag }, async ({
  page,
  request,
  workspaceId,
}) => {
  // The hit: searched, marked relevant, its automatic Add PDF fails (no free PDF), so it is "failed".
  await page.goto(`/#/workspaces/${workspaceId}?tab=search`)
  await page.getByLabel('Search query').fill('paperlab pagination fixture')
  const [started] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/search/runs') && r.request().method() === 'POST'),
    page.getByRole('button', { name: 'Start' }).click(),
  ])
  const { id: runId } = await started.json()
  await expect
    .poll(async () => (await (await request.get(`/api/workspaces/${workspaceId}/search/runs/${runId}`)).json()).status, { timeout: 15_000 })
    .toBe('exhausted')
  await page.reload()
  const row = page.locator('[data-slot="context-menu-trigger"]', { hasText: HIT_TITLE })
  await row.getByRole('button', { name: 'Result actions' }).click()
  await page.getByRole('menuitem', { name: 'Relevant', exact: true }).click()
  await expect(page.getByRole('menuitem', { name: 'Relevant', exact: true })).toHaveCount(0)
  await row.hover()
  const preview = page.locator('aside[aria-label="Result preview"]')
  await expect(preview.getByRole('heading', { name: HIT_TITLE })).toBeVisible()
  const [imported] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/search/hits/import') && r.request().method() === 'POST'),
    preview.getByRole('button', { name: 'Add PDF' }).click(),
  ])
  expect((await imported.json()).failed).toBe(1)

  // The same paper then saved without a PDF into the workspace: the failed hit links to it and awaits its PDF.
  const added = await request.post('/api/discovery/add', {
    data: { candidate: { title: HIT_TITLE, doi: HIT_DOI }, workspace_id: workspaceId, save_without_pdf: true },
  })
  expect(added.status()).toBe(201)

  await page.reload()
  await page.getByRole('tab', { name: /^Get PDFs/ }).click()
  const saved = page.getByRole('region', { name: 'Saved without a PDF' })
  await expect(saved.getByText(HIT_TITLE)).toBeVisible()

  await page.getByRole('tab', { name: /^Full-text review/ }).click()
  await expect(page.getByText('Needs the full text to assess')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Include' })).toHaveCount(0)

  await page.getByRole('tab', { name: /^PRISMA report/ }).click()
  const notRetrieved = page.locator('.contents', { hasText: 'Not retrieved' })
  await expect(notRetrieved.locator('dd')).toHaveText('1')

  // Upload from step 2.
  await page.getByRole('tab', { name: /^Get PDFs/ }).click()
  await saved.getByLabel(`Upload PDF for ${HIT_TITLE}`).setInputFiles(FIXTURE_FILE)
  await expect(saved.getByText(HIT_TITLE)).toHaveCount(0)

  await page.getByRole('tab', { name: /^Full-text review/ }).click()
  await expect(page.getByRole('button', { name: 'Include' })).toBeVisible()
  await expect(page.getByText('Needs the full text to assess')).toHaveCount(0)

  await page.getByRole('tab', { name: /^PRISMA report/ }).click()
  await expect(notRetrieved.locator('dd')).toHaveText('0')
})
