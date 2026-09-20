import { expect, test } from './fixtures'

// A normal browser has no desktop app: Settings shows no Desktop app section, and Connect Claude says how to start
// PaperLab with Docker. Inside the app both change (desktop/e2e). Read-only.
test('a browser gets no desktop-only settings, and Connect Claude says to start PaperLab with Docker', async ({ page }) => {
  await page.goto('/#/settings/claude')
  await expect(page.getByRole('heading', { level: 2, name: 'Connect Claude' })).toBeVisible() // the page is drawn

  // The section is not offered outside the app, so its own address falls back to the first section.
  await expect(page.getByRole('navigation', { name: 'Settings sections' }).getByRole('link', { name: 'Desktop app' })).toHaveCount(0)
  await page.goto('/#/settings/desktop')
  await expect(page.getByRole('region', { name: 'Model connections' })).toBeVisible()

  await expect(page.getByRole('region', { name: 'Desktop app' })).toHaveCount(0)
  await expect(page.getByRole('switch')).toHaveCount(0)

  await page.goto('/#/connect-claude')
  await expect(page.getByText('PaperLab must be running:')).toBeVisible()
  await expect(page.getByText('Keep the PaperLab app open')).toHaveCount(0)
})
