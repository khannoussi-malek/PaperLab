import type { APIRequestContext } from '@playwright/test'
import { expect, FIXTURE_FILE, removePaperAndNotes, test } from './fixtures'

// search_batch's per-source page size (workspace_search.py's PAGE_SIZE_BY_SOURCE) is far bigger than the 3-item
// pagination fixture (discovery_fake.py's PAGE_PAPERS), so the run's very first batch already stores every hit
// this query will ever find. It never reaches a terminal status on its own, though: SearchControls' default
// sources include "unpaywall", and with no contact email configured (a fresh stack's default) that source has no
// client, so search_batch's `if client is None: continue` skips it every pass without ever marking its cursor
// exhausted — the worker's `all(c.exhausted for c in cursors)` check can never be true, and it polls forever.
// Stopping the run explicitly (the real Stop control) is the only way to end it, so this test does that instead
// of waiting for a status the app cannot actually reach.
async function waitForHits(request: APIRequestContext, workspaceId: string) {
  await expect
    .poll(async () => (await (await request.get(`/api/workspaces/${workspaceId}/search/hits`)).json()).items.length, {
      timeout: 15_000,
    })
    .toBeGreaterThan(0)
}

test('search, screen, import a hit, then upload its PDF manually', async ({ page, request, workspaceId }) => {
  await page.goto(`/#/workspaces/${workspaceId}?tab=search`)
  await page.getByLabel('Search query').fill('bert')
  await page.getByRole('button', { name: 'Start' }).click()

  await waitForHits(request, workspaceId)
  await page.getByRole('button', { name: 'Stop' }).click()

  // HitTable's hit-pool query isn't invalidated by the run in the background; reload to pick up the stored hits.
  await page.reload()
  await expect(page.getByText(/[1-9]\d* in pool/)).toBeVisible()

  // "fixture 1" is deliberately avoided: discovery_fake.py's paginated arXiv feed derives entry 1's id as
  // "2609.00001", which collides with FREE_ARXIV_ID (the single-item Find Papers fixture's id). Whenever that
  // fixture's paper has already been imported by another spec sharing this stack, hit 1 merges onto its
  // ExternalRef and imports for free instead of failing. "fixture 2" derives "2609.00002", which never collides,
  // so it reliably has no free PDF and always needs manual acquisition below.
  const title = 'paperlab pagination fixture 2'
  await page.locator('button', { hasText: title }).click()

  const drawer = page.getByRole('dialog', { name: 'Review hit' })
  await drawer.getByRole('button', { name: 'Relevant', exact: true }).click()
  await expect(drawer).toHaveCount(0)

  await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/search/hits/import') && r.request().method() === 'POST'),
    page.getByRole('button', { name: 'Import all with PDF in this filter' }).click(),
  ])

  // fixture 2 has no free PDF, so the import fails and it needs manual acquisition.
  await page.getByRole('tab', { name: 'Manual acquisition' }).click()
  const uploadInput = page.getByLabel(`Upload PDF for ${title}`)
  await expect(uploadInput).toBeVisible()

  const [uploadResponse] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/upload') && r.request().method() === 'POST'),
    uploadInput.setInputFiles(FIXTURE_FILE),
  ])
  const uploaded = await uploadResponse.json()

  await expect(page.getByLabel(`Upload PDF for ${title}`)).toHaveCount(0)
  await removePaperAndNotes(request, uploaded.paper_id)
})
