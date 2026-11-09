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

// Fake titles (backend/app/providers/discovery_fake.py): other sources return the three PAPERS; the fake
// Semantic Scholar gives any seed all three PAPERS as references, and the closed paper two citing works (the free paper and Second Hop).
const SEED = 'PaperLab Closed Access Fixture' // a search hit (level 0): the other sources' fakes return the three PAPERS
const LEVEL_ONE = 'PaperLab Second Hop Fixture' // cites the seed: reached by "cited by"
const LEVEL_TWO = 'PaperLab Third Hop Fixture' // cited by the level-1 paper: reached by "it cites"

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

  const row = page.locator('[data-slot="context-menu-trigger"]', { hasText: SEED }).first()
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
  await page.getByRole('button', { name: 'Tree', exact: true }).click()
  await expect(page.getByRole('button', { name: new RegExp(`^${SEED}, level 0`) })).toBeVisible()
  const levelOne = page.getByRole('button', { name: new RegExp(`^${LEVEL_ONE}, level 1`) })
  await expect(levelOne).toBeVisible()

  // 3. Go further on the level-1 paper, then Run all: a level-2 box appears.
  await levelOne.click()
  const [branchResponse] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/search/branch') && r.request().method() === 'PUT'),
    page.getByRole('button', { name: 'Go further', exact: true }).click(),
  ])
  expect(branchResponse.ok()).toBe(true)
  await expect(page.getByRole('heading', { name: /^Snowball next \(1\)/ })).toBeVisible()
  await page.getByRole('button', { name: 'Run all' }).click()
  const levelTwo = page.getByRole('button', { name: new RegExp(`^${LEVEL_TWO}, level 2`) })
  await expect(levelTwo).toBeVisible({ timeout: 15_000 })

  // 4. Open the level-2 paper: its trail uses both arrow kinds.
  await levelTwo.click()
  const trail = page.getByRole('tabpanel', { name: 'Snowball tree' }).getByRole('region', { name: 'Why is this here?' })
  await expect(trail).toContainText('(it cites)')
  await expect(trail).toContainText('(cited by)')
})
