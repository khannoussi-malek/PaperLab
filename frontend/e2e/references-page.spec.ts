import type { APIRequestContext, Locator } from '@playwright/test'
import { expect, openReader, removePaperAndNotes, test } from './fixtures'
import { FREE_SOURCES_ON, MOVES_PAPER_SOURCES, readSourceSettings, setSourceSettings, type SourceSettings } from './paperSources'

const FREE = 'PaperLab Find Papers Fixture'
const LANDING = 'PaperLab Landing Page Fixture'
const CLOSED = 'PaperLab Closed Access Fixture'
const FAKE_DOI_PREFIX = '10.5555/paperlab-e2e-'
const tag = MOVES_PAPER_SOURCES

async function removeImportedFixtures(request: APIRequestContext) {
  const papers = await request.get('/api/papers')
  for (const paper of papers.ok() ? await papers.json() : []) {
    if (paper.doi?.startsWith(FAKE_DOI_PREFIX)) await removePaperAndNotes(request, paper.id)
  }
}

// A run killed after marking a fake To read (e.g. mid-test, before its own unmark) would otherwise linger on
// the owner's real To-read list until some other test's cleanup happened to catch it. Scoped to the whole
// library (no workspace param), so it finds a leftover mark regardless of which workspace queued it.
async function unqueueFakeReferences(request: APIRequestContext) {
  const page = await request.get('/api/references')
  if (!page.ok()) return
  const { to_read } = await page.json()
  for (const ref of to_read as { id: string; doi: string | null }[]) {
    if (ref.doi?.startsWith(FAKE_DOI_PREFIX)) await request.delete(`/api/references/${ref.id}/queue`)
  }
}

let owners: SourceSettings

test.beforeEach(async ({ request }) => {
  await removeImportedFixtures(request)
  await unqueueFakeReferences(request)
  owners = await readSourceSettings(request)
  await setSourceSettings(request, { enabled: FREE_SOURCES_ON })
})

test.afterEach(async ({ request }) => {
  await removeImportedFixtures(request)
  await unqueueFakeReferences(request)
  await setSourceSettings(request, owners)
})

const rowOf = (scope: Locator, title: string) => scope.locator('.reference-row').filter({ hasText: title })

test('marks To read in a tab, keeps it through a Refresh, and lists it on the page in its workspace', { tag }, async ({
  page, request, paperId, secondPaperId, tablePaperId, workspaceId,
}) => {
  for (const id of [paperId, secondPaperId, tablePaperId]) {
    expect((await request.put(`/api/workspaces/${workspaceId}/papers/${id}`)).status()).toBe(204)
  }

  await openReader(page, paperId)
  await page.getByRole('tab', { name: 'References' }).click()
  const firstTab = page.getByRole('complementary', { name: 'References' })
  await expect(firstTab.locator('.reference-row')).toHaveCount(3, { timeout: 30_000 })
  // A killed earlier run's fakes could already be queued; start clean.
  for (const title of [FREE, LANDING, CLOSED]) {
    const toggle = rowOf(firstTab, title).getByRole('button', { name: /^To read:/ })
    if ((await toggle.getAttribute('aria-pressed')) === 'true') await toggle.click()
  }

  await openReader(page, secondPaperId)
  await page.getByRole('tab', { name: 'References' }).click()
  const secondTab = page.getByRole('complementary', { name: 'References' })
  await expect(secondTab.locator('.reference-row')).toHaveCount(3, { timeout: 30_000 })

  await openReader(page, paperId)
  await page.getByRole('tab', { name: 'References' }).click()
  const panel = page.getByRole('complementary', { name: 'References' })
  await expect(panel.locator('.reference-row')).toHaveCount(3)
  await rowOf(panel, CLOSED).getByRole('button', { name: /^To read:/ }).click()
  await expect(rowOf(panel, CLOSED).getByRole('button', { name: /^To read:/ })).toHaveAttribute('aria-pressed', 'true')

  await page.getByRole('button', { name: 'Refresh' }).click()
  await expect(panel.getByText('Fetching references…')).toBeVisible()
  await expect(panel.locator('.reference-row')).toHaveCount(3, { timeout: 30_000 })
  await expect(rowOf(panel, CLOSED).getByRole('button', { name: /^To read:/ })).toHaveAttribute('aria-pressed', 'true')

  await page.goto(`/#/references?workspace=${workspaceId}`)
  await expect(page.locator('.references-coverage')).toContainText('From the references of 2 of your 3 papers.')
  await expect(page.locator('.unfetched-papers .unfetched-paper')).toHaveCount(1)
  await expect(rowOf(page.getByRole('region', { name: 'To read' }), CLOSED)).toBeVisible()
  const cited = page.getByRole('region', { name: 'Cited by several of your papers' })
  for (const title of [FREE, LANDING, CLOSED]) {
    await expect(rowOf(cited, title)).toContainText('Cited by 2 of your papers')
  }
  const citing = page.getByRole('region', { name: 'Citing several of your papers' })
  await expect(rowOf(citing, FREE)).toContainText('Cites 2 of your papers')
  await expect(citing.locator('.reference-row')).toHaveCount(1)

  await page.getByRole('button', { name: /^Fetch references for/ }).click()
  await expect(page.locator('.references-coverage')).toContainText('3 of your 3 papers.', { timeout: 30_000 })
  await expect(page.locator('.unfetched-papers')).toHaveCount(0)
  for (const title of [FREE, LANDING, CLOSED]) {
    await expect(rowOf(cited, title)).toContainText('Cited by 3 of your papers')
  }
  // Still only the free fixture cites back (the fake's /citations answers every paper the same way).
  await expect(rowOf(citing, FREE)).toContainText('Cites 3 of your papers')
  await expect(citing.locator('.reference-row')).toHaveCount(1)

  await rowOf(cited, FREE).getByRole('button', { name: /^To read:/ }).click()
  await expect(page.locator('.reference-list').first().locator('.reference-row').first()).toContainText(FREE, { timeout: 5000 })

  await rowOf(page.getByRole('region', { name: 'To read' }), FREE).getByRole('button', { name: 'Import' }).click()
  // An imported reference drops out of every section here (unlike the per-paper References tab's own row, which
  // switches to "In library"): the page only ranks references still outside the library.
  await expect(page.locator('.reference-row').filter({ hasText: FREE })).toHaveCount(0)

  await page.reload()
  await expect(page.locator('.reference-row').filter({ hasText: FREE })).toHaveCount(0)
  await expect(page.locator('.references-coverage')).toContainText('3 of your 4 papers.')
  expect((await request.get(`/api/workspaces/${workspaceId}/papers`)).ok()).toBe(true)

  await rowOf(page.getByRole('region', { name: 'To read' }), CLOSED).getByRole('button', { name: /^To read:/ }).click()
  await expect(page.getByRole('heading', { name: 'To read' })).toBeFocused()

  await page.goto('/#/')
  await page.getByRole('link', { name: 'References' }).click()
  await expect(page).toHaveURL('/#/references')
  await expect(page.getByRole('combobox', { name: 'Workspace' })).toHaveText('Whole library')
})
