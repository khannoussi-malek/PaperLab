import type { APIRequestContext, Locator, Page } from '@playwright/test'
import { expect, removePaperAndNotes, test } from './fixtures'

// The API runs with DISCOVERY_PROVIDER=fake (backend/app/providers/discovery_fake.py): every search and every
// suggestion answers these three papers, and nothing reaches OpenAlex or Semantic Scholar.
const FREE = 'PaperLab Find Papers Fixture'
const LANDING = 'PaperLab Landing Page Fixture'
const CLOSED = 'PaperLab Closed Access Fixture'
const FAKE_DOI_PREFIX = '10.5555/paperlab-e2e-'
const QUERY_LABEL = 'Title, DOI, arXiv ID or OpenAlex ID'

// A paper's DOI is unique and the fake's are fixed, so this file's tests take turns; no other spec adds them.
test.describe.configure({ mode: 'serial' })

async function removeFoundPapers(request: APIRequestContext) {
  const papers = await request.get('/api/papers')
  for (const paper of papers.ok() ? await papers.json() : []) {
    if (paper.doi?.startsWith(FAKE_DOI_PREFIX)) await removePaperAndNotes(request, paper.id)
  }
}

test.beforeEach(async ({ request }) => {
  await removeFoundPapers(request) // a killed run's leftovers would show as "In library"
  const found = await request.get('/api/discovery/search?q=fixture')
  const titles = found.ok() ? (await found.json()).map((c: { title: string }) => c.title) : []
  expect(titles, 'start the API with DISCOVERY_PROVIDER=fake (see the roadmap Commands)').toEqual([FREE, LANDING, CLOSED])
})

test.afterEach(async ({ request }) => {
  await removeFoundPapers(request)
})

const rowOf = (scope: Locator, title: string) => scope.locator('.candidate-row').filter({ hasText: title })

async function searchFromHere(page: Page): Promise<Locator> {
  await page.getByRole('button', { name: 'Find papers' }).click()
  const dialog = page.getByRole('dialog', { name: 'Find papers' })
  await dialog.getByRole('textbox', { name: QUERY_LABEL }).fill('fixture')
  await dialog.getByRole('button', { name: 'Search' }).click()
  await expect(dialog.locator('.candidate-row')).toHaveCount(3)
  return dialog
}

/** Clicks Add on the row, waits for "In library", and returns the new paper's id. */
async function addFrom(row: Locator): Promise<string> {
  await row.getByRole('button', { name: 'Add' }).click()
  const inLibrary = row.getByRole('link', { name: 'In library' })
  await expect(inLibrary).toBeVisible()
  return (await inLibrary.getAttribute('href'))!.replace('#/papers/', '')
}

async function waitUntilReady(request: APIRequestContext, paperId: string) {
  await expect
    .poll(async () => (await (await request.get(`/api/papers/${paperId}`)).json()).status, { timeout: 30_000 })
    .toBe('ready')
}

test('find a paper from the library, add its free PDF, and see it in the library', async ({ page, request }) => {
  await page.goto('/')
  const dialog = await searchFromHere(page)

  await expect(rowOf(dialog, FREE).getByText('PDF', { exact: true })).toBeVisible()
  await expect(rowOf(dialog, CLOSED).getByText('No free PDF')).toBeVisible()
  await expect(rowOf(dialog, CLOSED).getByRole('button', { name: 'Add' })).toHaveCount(0)
  await expect(rowOf(dialog, CLOSED).getByRole('link', { name: 'Open page' })).toHaveAttribute(
    'href',
    `https://doi.org/${FAKE_DOI_PREFIX}closed`,
  )

  const paperId = await addFrom(rowOf(dialog, FREE))
  await waitUntilReady(request, paperId)

  await page.keyboard.press('Escape')
  const libraryRow = page.locator('.paper-row').filter({ has: page.locator(`a[href="#/papers/${paperId}"]`) })
  await expect(libraryRow).toContainText(FREE)
})

test('a paper whose PDF link is a web page says no free PDF was found', async ({ page }) => {
  await page.goto('/')
  const dialog = await searchFromHere(page)

  await rowOf(dialog, LANDING).getByRole('button', { name: 'Add' }).click()

  await expect(rowOf(dialog, LANDING).getByRole('alert')).toContainText('No free PDF was found for this paper.')
  await expect(rowOf(dialog, LANDING).getByRole('button', { name: 'Add' })).toBeEnabled()
})

test('a paper found from a workspace joins that workspace', async ({ page, request, workspaceId }) => {
  await page.goto(`/#/workspaces/${workspaceId}`)
  const dialog = await searchFromHere(page)

  const paperId = await addFrom(rowOf(dialog, FREE))

  const members: { id: string }[] = await (await request.get(`/api/workspaces/${workspaceId}/papers`)).json()
  expect(members.map((paper) => paper.id)).toContain(paperId)
  await waitUntilReady(request, paperId)
})
