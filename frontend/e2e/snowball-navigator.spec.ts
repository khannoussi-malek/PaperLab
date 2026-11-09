import type { APIRequestContext } from '@playwright/test'
import { ask, expect, test } from './fixtures'

async function waitForRunToFinish(request: APIRequestContext, workspaceId: string, runId: string) {
  await expect
    .poll(async () => (await (await request.get(`/api/workspaces/${workspaceId}/search/runs/${runId}`)).json()).status, {
      timeout: 15_000,
    })
    .toBe('exhausted')
}

// Fake titles (backend/app/providers/discovery_fake.py): the closed paper is a search hit; Second Hop cites it.
const SEED = 'PaperLab Closed Access Fixture'
const SECOND = 'PaperLab Second Hop Fixture'

test('the snowball navigator walks from a seed to a citing paper and asks the AI about it', async ({ page, request, workspaceId, llmConnection }) => {
  void llmConnection // the AI chat needs a model; the fixture adds one and removes it after the test

  // 1. Search, then mark the seed relevant.
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
  await page.getByRole('menuitem', { name: 'Relevant', exact: true }).click()
  await expect(page.getByRole('menuitem', { name: 'Relevant', exact: true })).toHaveCount(0)

  // 2. The Snowball tree tab opens in Navigate.
  await page.getByRole('tab', { name: /^Snowball tree/ }).click()
  await expect(page.getByRole('button', { name: 'Navigate' })).toHaveAttribute('aria-pressed', 'true')

  // 3. Start from the seed: nothing is fetched yet.
  await page.getByLabel('Start from a paper').fill('Closed Access')
  await page.getByRole('button', { name: new RegExp(`^${SEED}`) }).click()
  const crumbs = page.getByRole('navigation', { name: 'Snowball path' }).getByRole('button')
  await expect(page.getByRole('tab', { name: 'Papers it cites (not fetched)' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Papers citing it (not fetched)' })).toBeVisible()

  // 4. Fetch: the rows appear.
  await page.getByRole('button', { name: 'Find citing & cited papers' }).click()
  await page.getByRole('tab', { name: /^Papers citing it \(\d+\)$/ }).click()
  const stepIn = page.getByRole('button', { name: /^Step in/, description: SECOND })
  await expect(stepIn).toBeVisible({ timeout: 15_000 })

  // 5. Grab the Second Hop row.
  await page.getByRole('button', { name: /Grab next papers/, description: SECOND }).click()
  await expect(page.getByText(/✓ grabbed/)).toBeVisible({ timeout: 30_000 })

  // 6. Step in: root, seed, Second Hop.
  const before = await crumbs.count()
  await stepIn.click()
  await expect(crumbs).toHaveCount(before + 1)
  await expect(crumbs).toHaveCount(3)
  await expect(crumbs.last()).toHaveAttribute('aria-current', /.+/)

  // 7. Ask the AI: the paper has no file, so it reads the abstract only.
  const panel = page.getByRole('complementary', { name: 'Ask the AI' })
  await expect(panel.getByText(/^Reads: .*\(abstract only\)$/)).toBeVisible()
  const answer = await ask(page, 'What is this paper about?', 30_000)
  await expect(answer.locator('.chat-answer-text')).not.toBeEmpty()

  // 8. The first breadcrumb entry takes us back to the start.
  await crumbs.first().click()
  await expect(crumbs).toHaveCount(1)
})
