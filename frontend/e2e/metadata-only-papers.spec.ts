import { fileURLToPath } from 'node:url'
import type { APIRequestContext, Page } from '@playwright/test'
import { expect, removePaperAndNotes, test } from './fixtures'
import { FREE_SOURCES_ON, MOVES_PAPER_SOURCES, readSourceSettings, setSourceSettings, type SourceSettings } from './paperSources'

// Papers saved without a PDF. The API runs with DISCOVERY_PROVIDER=fake (backend/app/providers/discovery_fake.py):
// its "Landing Page" paper has a link that is a web page, so adding it answers "No free PDF was found".
const LANDING = 'PaperLab Landing Page Fixture'
const FAKE_DOI_PREFIX = '10.5555/paperlab-e2e-'
const BIB_TITLE = 'PaperLab E2E No PDF Entry'
const BIB = fileURLToPath(new URL('./fixtures/zotero/no-pdf.bib', import.meta.url))
const tag = MOVES_PAPER_SOURCES // these turn paper sources on, so they run one at a time after the parallel specs

test.describe.configure({ mode: 'serial' })

async function removeLeftovers(request: APIRequestContext) {
  const papers = await request.get('/api/papers')
  for (const paper of papers.ok() ? ((await papers.json()) as { id: string; title: string; doi: string | null }[]) : []) {
    if (paper.title === BIB_TITLE || paper.doi?.startsWith(FAKE_DOI_PREFIX)) await removePaperAndNotes(request, paper.id)
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

/** Opens the paper and checks the details panel stands in for the PDF: no file request, no PDF error. */
async function expectDetailsInPlaceOfPdf(page: Page, id: string) {
  const fileRequests: string[] = []
  page.on('request', (r) => {
    if (r.url().includes(`/api/papers/${id}/file`)) fileRequests.push(r.url())
  })
  await page.goto(`/#/papers/${id}`)
  const details = page.getByRole('region', { name: 'Paper details' })
  await expect(details.getByText('No PDF yet')).toBeVisible()
  await expect(details.getByText(/^Details from /)).toBeVisible()
  await page.waitForTimeout(1000) // a request, if one were coming, is made by now
  expect(fileRequests).toEqual([])
  await expect(page.getByText('Could not open PDF')).toHaveCount(0)
  return details
}

test('a paper with no free PDF is saved without one, badged, and opens on its details', { tag }, async ({ page }) => {
  const id = await saveLandingWithoutPdf(page)

  await page.goto('/')
  const row = page.locator('.paper-row').filter({ has: page.locator(`a[href="#/papers/${id}"]`) })
  await expect(row).toContainText(LANDING)
  await expect(row.locator('.no-pdf')).toHaveText('No PDF yet')

  const details = await expectDetailsInPlaceOfPdf(page, id)
  await expect(details.getByRole('heading', { name: LANDING })).toBeVisible()
  await expect(details.getByRole('link', { name: `doi:${FAKE_DOI_PREFIX}landing` })).toBeVisible()
})

test('a .bib imported with fetching off and save-without-PDF on saves the entry without a PDF', { tag }, async ({
  page,
  workspaceId,
}) => {
  await page.goto(`/#/workspaces/${workspaceId}`)
  await page.getByRole('button', { name: 'Import from Zotero' }).click()
  const dialog = page.getByRole('dialog', { name: 'Import from Zotero' })
  await dialog.getByLabel('References file').setInputFiles(BIB)
  await expect(dialog.getByRole('radio', { name: 'This workspace' })).toBeChecked()
  await dialog.getByRole('switch', { name: 'Fetch free PDFs for entries without one' }).click() // off: no network
  await expect(dialog.getByRole('switch', { name: 'Save the others without a PDF' })).toBeChecked() // on by default
  await dialog.getByRole('button', { name: 'Import', exact: true }).click()
  await expect(dialog.getByRole('heading', { name: 'Import finished' })).toBeVisible({ timeout: 60_000 })
  await expect(dialog.getByText(/1 saved without a PDF/)).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()

  const row = page.locator('.paper-row').filter({ hasText: BIB_TITLE })
  await expect(row.locator('.no-pdf')).toHaveText('No PDF yet')
  const href = (await row.getByRole('link').first().getAttribute('href'))!
  const details = await expectDetailsInPlaceOfPdf(page, href.replace('#/papers/', ''))
  await expect(details.getByText('A saved-without-PDF abstract from Zotero.')).toBeVisible()
})

test('deleting a paper saved without a PDF removes it for good', { tag }, async ({ page, request }) => {
  const id = await saveLandingWithoutPdf(page)
  await page.goto('/')
  const row = page.locator('.paper-row').filter({ has: page.locator(`a[href="#/papers/${id}"]`) })
  await expect(row).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept())
  const [deleted] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith(`/api/papers/${id}`) && r.request().method() === 'DELETE'),
    row.getByRole('button', { name: 'Delete' }).click(),
  ])
  expect(deleted.status()).toBe(204)
  await expect(row).toHaveCount(0)

  await page.reload()
  await expect(page.locator('.paper-row').filter({ hasText: LANDING })).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect((await request.get(`/api/papers/${id}`)).status()).toBe(404)
})
