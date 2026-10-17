import { expect, test } from './fixtures'

test.use({ viewport: { width: 390, height: 844 } })

test('at 390 px the tabs scroll, the active tab stays visible and the navigation is folded', async ({ page, workspaceId }) => {
  await page.goto(`/#/workspaces/${workspaceId}?tab=prisma`)

  await expect(page.getByRole('tab', { name: /^PRISMA report/ })).toBeInViewport()
  await expect(page.getByRole('navigation', { name: 'Views' })).toBeHidden()
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 390)).toBe(true)
})
