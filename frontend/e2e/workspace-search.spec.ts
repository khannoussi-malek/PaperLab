import type { APIRequestContext } from '@playwright/test'
import { expect, FIXTURE_FILE, removePaperAndNotes, test } from './fixtures'

// search_batch's per-source page size (workspace_search.py's PAGE_SIZE_BY_SOURCE) is far bigger than the 3-item
// pagination fixture (discovery_fake.py's PAGE_PAPERS), so the run's very first batch already stores every hit
// this query will ever find, and exhausts every source's cursor in that same batch. This run used to never
// reach a terminal status on its own: SearchControls hard-coded "unpaywall" into every Start click, and with no
// contact email configured (a fresh stack's default) that source had no client, so search_batch's
// `if client is None: continue` skipped it every pass without ever marking its cursor exhausted — the worker's
// `all(c.exhausted for c in cursors)` check could never become true, and it polled forever. Both halves of that
// are fixed now: SearchControls only ever sends the sources actually enabled in settings, never unpaywall
// (which has no search role at all — C1), and the worker's own cursor error-caps, iteration cap and wall-clock
// deadline (C2) independently guarantee termination besides. So this test polls the run's own status via the
// API for "exhausted", instead of clicking the Stop control to force an end it no longer needs — this exercises
// the actual fixed behavior end to end, not a workaround for it.
async function waitForRunToFinish(request: APIRequestContext, workspaceId: string, runId: string) {
  await expect
    .poll(async () => (await (await request.get(`/api/workspaces/${workspaceId}/search/runs/${runId}`)).json()).status, {
      timeout: 15_000,
    })
    .toBe('exhausted')
}

test('search, screen, import a hit, then upload its PDF manually', async ({ page, request, workspaceId }) => {
  await page.goto(`/#/workspaces/${workspaceId}?tab=search`)
  await page.getByLabel('Search query').fill('bert')
  const [startResponse] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/search/runs') && r.request().method() === 'POST'),
    page.getByRole('button', { name: 'Start' }).click(),
  ])
  const { id: runId } = await startResponse.json()

  await waitForRunToFinish(request, workspaceId, runId)

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
