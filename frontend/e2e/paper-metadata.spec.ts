import { FIXTURE_TITLE, expect, openReader, test } from './fixtures'

test('a retracted paper shows a banner above the pages, and only while it is retracted', async ({
  page,
  request,
  paperId,
}) => {
  const line = await openReader(page, paperId)
  await expect(page.getByRole('heading', { name: FIXTURE_TITLE })).toBeVisible() // the paper has loaded
  const banner = page.locator('.retraction-banner')
  await expect(banner).toHaveCount(0)

  // Enrichment sets the flag from OpenAlex, which the E2E stack never calls; a correction sets it the same way.
  expect((await request.patch(`/api/papers/${paperId}`, { data: { is_retracted: true } })).status()).toBe(200)
  await page.reload()
  await expect(line).toBeVisible()
  await expect(banner).toBeVisible()
  await expect(banner).toHaveAttribute('role', 'alert')
  await expect(banner).toContainText('This paper has been retracted')
  // Above the pages, never over them: the banner ends before page 1 begins.
  const bannerBox = await banner.boundingBox()
  const pageBox = await page.locator('.pdf-page[data-page="1"]').boundingBox()
  expect(bannerBox!.y + bannerBox!.height).toBeLessThanOrEqual(pageBox!.y)

  expect((await request.patch(`/api/papers/${paperId}`, { data: { is_retracted: false } })).status()).toBe(200)
  await page.reload()
  await expect(line).toBeVisible()
  await expect(page.getByRole('heading', { name: FIXTURE_TITLE })).toBeVisible()
  await expect(banner).toHaveCount(0)
})
