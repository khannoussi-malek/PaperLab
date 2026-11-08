import type { APIRequestContext } from '@playwright/test'
import { expect, test } from './fixtures'

// Same polling helper as workspace-snowball-prisma.spec.ts (not exported there).
async function waitForRunToFinish(request: APIRequestContext, workspaceId: string, runId: string) {
  await expect
    .poll(async () => (await (await request.get(`/api/workspaces/${workspaceId}/search/runs/${runId}`)).json()).status, {
      timeout: 15_000,
    })
    .toBe('exhausted')
}

// Fake titles (backend/app/providers/discovery_fake.py): the search returns the pagination fixtures; the fake
// Semantic Scholar gives any seed all three PAPERS as references, and the closed paper one extra citing work.
const SEED = 'paperlab pagination fixture 2'
const LEVEL_ONE = 'PaperLab Closed Access Fixture' // only ever a reference, so reached by "it cites"
const LEVEL_TWO = 'PaperLab Second Hop Fixture' // cites the closed paper only, so reached by "cited by"

test('the snowball tree shows levels, runs the next hop, and explains a level-2 paper', async ({ page, request, workspaceId }) => {
  // 1. Search, mark the seed relevant in the UI, snowball it through the API (the tree is what is under test).
  await page.goto(`/#/workspaces/${workspaceId}?tab=search`)
  await page.getByLabel('Search query').fill('paperlab pagination fixture')
  const [startResponse] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/search/runs') && r.request().method() === 'POST'),
    page.getByRole('button', { name: 'Start' }).click(),
  ])
  await waitForRunToFinish(request, workspaceId, (await startResponse.json()).id)
  await page.reload()
  await expect(page.getByText(/[1-9]\d* results \(after filters\)/)).toBeVisible()

  const row = page.locator('[data-slot="context-menu-trigger"]', { hasText: SEED })
  await row.getByRole('button', { name: 'Result actions' }).click()
  await page.getByRole('menuitem', { name: 'Relevant', exact: true }).click() // exact: "Not relevant…" shares the menu
  await expect(page.getByRole('menuitem', { name: 'Relevant', exact: true })).toHaveCount(0)

  const hits = await (await request.get(`/api/workspaces/${workspaceId}/search/hits?limit=50`)).json()
  const seed = hits.items.find((h: { title: string }) => h.title === SEED)
  expect(seed).toBeTruthy()
  const snowball = await request.post(`/api/workspaces/${workspaceId}/search/snowball`, {
    data: { seed_hit_ids: [seed.id], backward: true, forward: true },
  })
  expect(snowball.ok()).toBe(true)
  expect((await snowball.json()).skipped_seeds).toEqual([])

  // 2. The tree: the search paper at level 0, what it cites at level 1.
  await page.getByRole('tab', { name: /^Snowball tree/ }).click()
  await expect(page.getByRole('button', { name: new RegExp(`^${SEED}, level 0`) })).toBeVisible()
  const levelOne = page.getByRole('button', { name: new RegExp(`^${LEVEL_ONE}, level 1`) })
  await expect(levelOne).toBeVisible()

  // 3. Go further on the level-1 paper, then Run all: a level-2 box appears.
  await levelOne.click()
  const [branchResponse] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/search/branch') && r.request().method() === 'PUT'),
    page.getByRole('button', { name: 'Go further' }).click(),
  ])
  expect(branchResponse.ok()).toBe(true)
  await expect(page.getByRole('heading', { name: /^Snowball next \(1\)/ })).toBeVisible()
  await page.getByRole('button', { name: 'Run all' }).click()
  const levelTwo = page.getByRole('button', { name: new RegExp(`^${LEVEL_TWO}, level 2`) })
  await expect(levelTwo).toBeVisible({ timeout: 15_000 })

  // 4. Open the level-2 paper: its trail uses both arrow kinds.
  await levelTwo.click()
  const trail = page.getByText('Why is this here?').locator('..')
  await expect(trail).toContainText('(it cites)')
  await expect(trail).toContainText('(cited by)')
})
