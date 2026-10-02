import type { APIRequestContext, Page } from '@playwright/test'
import { expect, test } from './fixtures'

async function searchAndWait(page: Page, request: APIRequestContext, workspaceId: string) {
  await page.goto(`/#/workspaces/${workspaceId}?tab=search`)
  await page.getByLabel('Search query').fill('bert')
  const [started] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/search/runs') && r.request().method() === 'POST'),
    page.getByRole('button', { name: 'Start' }).click(),
  ])
  const { id: runId } = await started.json()
  await expect
    .poll(async () => (await (await request.get(`/api/workspaces/${workspaceId}/search/runs/${runId}`)).json()).status, {
      timeout: 15_000,
    })
    .toBe('exhausted')
  await page.reload()
  await expect(page.getByText(/[1-9]\d* in pool/)).toBeVisible()
}

function row(page: Page, title: string) {
  return page.locator('[data-slot="context-menu-trigger"]', { hasText: title })
}

test('the ranked sort learns from decisions and keeps only unscreened hits', async ({ page, request, workspaceId }) => {
  await searchAndWait(page, request, workspaceId)
  await page.getByLabel('Sort hits').selectOption('ranked')
  await expect(
    page.getByText("Ranking learns once you've marked at least one hit relevant and one not relevant."),
  ).toBeVisible()

  await row(page, 'paperlab pagination fixture 1').getByRole('button', { name: 'Hit actions' }).click()
  await page.getByRole('menuitem', { name: 'Relevant', exact: true }).click()
  await row(page, 'paperlab pagination fixture 3').getByRole('button', { name: 'Hit actions' }).click()
  await page.getByRole('menuitem', { name: 'Not relevant…' }).click()
  await page.getByRole('menuitem', { name: 'wrong_topic' }).click()

  await expect(page.getByText(/Showing the 1 most likely relevant of 1 unscreened\./)).toBeVisible()
  await expect(row(page, 'paperlab pagination fixture 2')).toBeVisible()
  await expect(row(page, 'paperlab pagination fixture 1')).toHaveCount(0)

  await page.reload()
  await expect(page.getByLabel('Sort hits')).toHaveValue('ranked')

  const prisma = await (await request.get(`/api/workspaces/${workspaceId}/search/prisma`)).json()
  expect(prisma.automation[0]).toContain('prioritised with active learning')
})
