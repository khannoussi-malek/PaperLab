import type { APIRequestContext, Locator } from '@playwright/test'
import { expect, openReader, removePaperAndNotes, test } from './fixtures'
import { FREE_SOURCES_ON, MOVES_PAPER_SOURCES, readSourceSettings, setSourceSettings, type SourceSettings } from './paperSources'

// The API runs with DISCOVERY_PROVIDER=fake (backend/app/providers/discovery_fake.py): the `paperId` fixture paper
// ("PaperLab E2E Fixture") is wired in the fake to cite these three M19 fixtures, and to be cited by the free one.
const FREE = 'PaperLab Find Papers Fixture'
const LANDING = 'PaperLab Landing Page Fixture'
const CLOSED = 'PaperLab Closed Access Fixture'
// Same fixed DOIs find-papers.spec.ts imports under: importing FREE here creates the same paper that spec adds.
const FAKE_DOI_PREFIX = '10.5555/paperlab-e2e-'
// References come from Semantic Scholar, and the owner may have switched it off (or OpenAlex on, which the fake
// doesn't cover): the test sets the sources, so it runs after the parallel specs, one at a time (playwright.config.ts).
// That also keeps it from racing find-papers.spec.ts over the same fixed DOIs.
const tag = MOVES_PAPER_SOURCES

async function removeImportedFixtures(request: APIRequestContext) {
  const papers = await request.get('/api/papers')
  for (const paper of papers.ok() ? await papers.json() : []) {
    if (paper.doi?.startsWith(FAKE_DOI_PREFIX)) await removePaperAndNotes(request, paper.id)
  }
}

// The owner's switches and email, put back after each test (D76).
let owners: SourceSettings

test.beforeEach(async ({ request }) => {
  await removeImportedFixtures(request) // a killed run's leftovers would show as "In library"
  owners = await readSourceSettings(request)
  await setSourceSettings(request, { enabled: FREE_SOURCES_ON })
})

test.afterEach(async ({ request }) => {
  await removeImportedFixtures(request)
  await setSourceSettings(request, owners)
})

const rowOf = (scope: Locator, title: string) => scope.locator('.reference-row').filter({ hasText: title })

test('auto-fetches references on open, switches Cited/Citing, and imports one with a free PDF', { tag }, async ({ page, paperId }) => {
  await openReader(page, paperId)
  await page.getByRole('tab', { name: 'References' }).click()
  await expect(page).toHaveURL(new RegExp(`#/papers/${paperId}\\?tab=references$`))

  // Opening the tab alone queues the fetch (D78): no button to click.
  const panel = page.getByRole('complementary', { name: 'References' })
  await expect(panel.getByText('Fetching references…')).toBeVisible()

  // Cited (the default direction): the three papers this paper cites.
  await expect(panel.locator('.reference-row')).toHaveCount(3, { timeout: 30_000 })
  // LANDING's Semantic Scholar record lists a link too (a landing page, not a real PDF), so it badges the same as
  // FREE here — the mismatch only surfaces on Import, exactly as Find papers' Add does for the same fixture.
  await expect(rowOf(panel, FREE).getByText('PDF', { exact: true })).toBeVisible()
  await expect(rowOf(panel, LANDING).getByText('PDF', { exact: true })).toBeVisible()
  await expect(rowOf(panel, CLOSED).getByText('No free PDF')).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Refresh' })).toBeVisible()

  // Citing: only the free fixture cites this paper back. The worker fetches both directions together, so the
  // rows are already there — no second fetch to wait for.
  await panel.getByRole('tab', { name: 'Citing' }).click()
  await expect(panel.locator('.reference-row')).toHaveCount(1)
  await expect(rowOf(panel, FREE)).toBeVisible()

  await panel.getByRole('tab', { name: 'Cited' }).click()
  await expect(panel.locator('.reference-row')).toHaveCount(3)

  await rowOf(panel, FREE).getByRole('button', { name: 'Import' }).click()
  await expect(rowOf(panel, FREE).getByRole('link', { name: 'In library' })).toBeVisible()
})

test('shows why a refresh failed', { tag }, async ({ page, paperId }) => {
  await openReader(page, paperId)
  await page.getByRole('tab', { name: 'References' }).click()

  const panel = page.getByRole('complementary', { name: 'References' })
  await expect(panel.locator('.reference-row')).toHaveCount(3, { timeout: 30_000 })

  await page.route('**/api/papers/*/references/refresh', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Refreshing failed for this test.' }) }),
  )
  await panel.getByRole('button', { name: 'Refresh' }).click()
  await expect(panel.getByText('Refreshing failed for this test.')).toBeVisible()
  await page.unroute('**/api/papers/*/references/refresh')
})
