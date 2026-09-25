import { expect, test } from './fixtures'

// Read-only: Settings shows where to star the project and follow its updates, opening outside the app.
test('settings links to starring the repository and following on LinkedIn, in a new window', async ({ page }) => {
  await page.goto('/#/settings')

  const star = page.getByRole('link', { name: 'Star PaperLab on GitHub' })
  await expect(star).toHaveAttribute('href', 'https://github.com/khannoussi-malek/PaperLab')
  await expect(star).toHaveAttribute('target', '_blank')
  const follow = page.getByRole('link', { name: 'Follow on LinkedIn' })
  await expect(follow).toHaveAttribute('href', 'https://www.linkedin.com/company/os-paperlab')
  await expect(follow).toHaveAttribute('target', '_blank')
})
