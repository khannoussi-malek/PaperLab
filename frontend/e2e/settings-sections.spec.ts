import { expect, test } from './fixtures'

const nav = (page: import('@playwright/test').Page) =>
  page.getByRole('navigation', { name: 'Settings sections' })

test('Settings shows one section at a time, chosen from the list beside it', async ({ page }) => {
  await page.goto('/#/settings')

  // The first section opens, and only it.
  await expect(page.getByRole('region', { name: 'Model connections' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Paper sources' })).toHaveCount(0)
  await expect(nav(page).getByRole('link', { name: 'Model connections' })).toHaveAttribute('aria-current', 'page')

  await nav(page).getByRole('link', { name: 'Paper sources' }).click()
  await expect(page).toHaveURL(/#\/settings\/sources$/)
  await expect(page.getByRole('region', { name: 'Paper sources' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Model connections' })).toHaveCount(0)
  await expect(nav(page).getByRole('link', { name: 'Paper sources' })).toHaveAttribute('aria-current', 'page')

  // The address is the section, so a reload stays put.
  await page.reload()
  await expect(page.getByRole('region', { name: 'Paper sources' })).toBeVisible()

  // A misspelt section still opens Settings, on its first section.
  await page.goto('/#/settings/nonsense')
  await expect(page.getByRole('region', { name: 'Model connections' })).toBeVisible()
})
