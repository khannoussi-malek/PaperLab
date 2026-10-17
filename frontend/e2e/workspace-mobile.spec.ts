import type { APIRequestContext, Page } from '@playwright/test'
import { expect, test } from './fixtures'

test.use({ viewport: { width: 390, height: 844 } })

test('at 390 px the tabs scroll, the active tab stays visible and the navigation is folded', async ({ page, workspaceId }) => {
  await page.goto(`/#/workspaces/${workspaceId}?tab=prisma`)

  await expect(page.getByRole('tab', { name: /^PRISMA report/ })).toBeInViewport()
  await expect(page.getByRole('navigation', { name: 'Views' })).toBeHidden()
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 390)).toBe(true)
})

// M71: a result row gives its title the whole first line at 390 px, and keeps one 44 px line at 1440.
async function searchFixture(page: Page, request: APIRequestContext, workspaceId: string) {
  await page.goto(`/#/workspaces/${workspaceId}?tab=search`)
  await page.getByLabel('Search query').fill('paperlab pagination fixture')
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
  const list = page.getByLabel('Result list')
  await expect(list.getByText(/paperlab pagination fixture/i).first()).toBeVisible()
  return list
}

test('at 390 px a result row gives its title the whole first line', async ({ page, request, workspaceId }) => {
  const list = await searchFixture(page, request, workspaceId)
  const title = await list.getByText(/paperlab pagination fixture/i).first().boundingBox()

  expect(title?.width ?? 0).toBeGreaterThan(250)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 390)).toBe(true)
})

test.describe('at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('a result row stays one 44 px line', async ({ page, request, workspaceId }) => {
    const list = await searchFixture(page, request, workspaceId)
    const row = list.locator('[aria-selected]').first()

    expect((await row.boundingBox())?.height).toBe(44)
  })
})
