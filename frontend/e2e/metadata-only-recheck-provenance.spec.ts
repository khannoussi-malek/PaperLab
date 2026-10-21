import type { APIRequestContext, Page } from '@playwright/test'
import { expect, FIXTURE_FILE, removePaperAndNotes, test } from './fixtures'
import { FREE_SOURCES_ON, MOVES_PAPER_SOURCES, readSourceSettings, setSourceSettings, type SourceSettings } from './paperSources'

// The weekly re-check switch, and the Details dialog's provenance and history (PR 4). API runs with DISCOVERY_PROVIDER=fake.
// Not covered here: the library's "found PDFs" notice. Only the weekly job creates pdf_found events and nothing in the UI
// or API can trigger it, so the notice is covered by vitest and the backend job tests.
const LANDING = 'PaperLab Landing Page Fixture'
const EDITED = 'PaperLab Landing Page Fixture, edited'
const FAKE_DOI_PREFIX = '10.5555/paperlab-e2e-'
const tag = MOVES_PAPER_SOURCES // these change paper-source settings, so they run one at a time after the parallel specs

test.describe.configure({ mode: 'serial' })

async function removeLeftovers(request: APIRequestContext) {
  const papers = await request.get('/api/papers')
  for (const paper of papers.ok() ? ((await papers.json()) as { id: string; doi: string | null }[]) : []) {
    if (paper.doi?.startsWith(FAKE_DOI_PREFIX)) await removePaperAndNotes(request, paper.id)
  }
}

let owners: SourceSettings
let ownersRecheck = true

async function recheckEnabled(request: APIRequestContext): Promise<boolean> {
  return ((await (await request.get('/api/paper-sources')).json()) as { pdf_recheck_enabled: boolean }).pdf_recheck_enabled
}

test.beforeEach(async ({ request }) => {
  await removeLeftovers(request)
  owners = await readSourceSettings(request)
  ownersRecheck = await recheckEnabled(request)
  await setSourceSettings(request, { enabled: FREE_SOURCES_ON })
})

test.afterEach(async ({ request }) => {
  await removeLeftovers(request)
  await setSourceSettings(request, owners)
  expect((await request.patch('/api/paper-sources', { data: { pdf_recheck_enabled: ownersRecheck } })).status()).toBe(200)
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

async function openDetails(page: Page) {
  await page.getByRole('button', { name: 'Edit details' }).click()
  return page.getByRole('dialog', { name: 'Edit details' })
}

test('the weekly re-check switch persists across a reload', { tag }, async ({ page, request }) => {
  await page.goto('/#/settings/sources')
  const recheck = page.getByRole('checkbox', { name: 'Look for free PDFs weekly for papers saved without one' })
  await expect(recheck).toBeVisible()
  if (!(await recheck.isChecked())) await recheck.click() // start from on, the default
  await expect.poll(() => recheckEnabled(request)).toBe(true)

  await recheck.click()
  await expect(recheck).not.toBeChecked()
  await expect.poll(() => recheckEnabled(request)).toBe(false)

  await page.reload()
  await expect(recheck).not.toBeChecked()
  expect(await recheckEnabled(request)).toBe(false)

  await recheck.click()
  await expect(recheck).toBeChecked()
  await expect.poll(() => recheckEnabled(request)).toBe(true)
})

test('the details dialog says where details came from, then "edited by you", then the PDF upload in History', { tag }, async ({
  page,
}) => {
  const id = await saveLandingWithoutPdf(page)
  await page.goto(`/#/papers/${id}`)

  let dialog = await openDetails(page)
  // Which source the fake candidate carries decides the label; any real details source or "a search result" is right.
  await expect(dialog.getByText(/^Title, authors and venue: from (Crossref|OpenAlex|Semantic Scholar|arXiv|a search result)$/)).toBeVisible()
  // Add's own lookup found no free copy, which counts as a check: the weekly re-check waits a week before repeating it
  await expect(dialog.getByText(/^Last checked for a free copy: .*, none found$/)).toBeVisible()

  await dialog.getByLabel('Title').fill(EDITED)
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(dialog).toBeHidden()
  // the reader toolbar's title (h1); the details panel repeats it as an h2
  await expect(page.getByRole('heading', { name: EDITED, level: 1 })).toBeVisible()

  dialog = await openDetails(page)
  await expect(dialog.getByText('Title, authors and venue: edited by you')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()

  const details = page.getByRole('region', { name: 'Paper details' })
  await details.getByLabel(`Upload PDF for ${EDITED}`).setInputFiles(FIXTURE_FILE)
  await expect(page.locator('.pdf-page[data-page="1"]')).toBeVisible({ timeout: 30_000 })

  dialog = await openDetails(page)
  await expect(dialog.getByRole('heading', { name: 'History' })).toBeVisible()
  await expect(dialog.getByText(/^PDF added .* \(uploaded\)$/)).toBeVisible()
})
