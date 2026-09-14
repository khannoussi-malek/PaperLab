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
  // Full opacity: the description must not render dimmer than the title (AA contrast).
  const color = (locator: import('@playwright/test').Locator) => locator.evaluate((el) => getComputedStyle(el).color)
  expect(await color(banner.locator('[data-slot="alert-description"]'))).toBe(
    await color(banner.locator('[data-slot="alert-title"]'))
  )

  expect((await request.patch(`/api/papers/${paperId}`, { data: { is_retracted: false } })).status()).toBe(200)
  await page.reload()
  await expect(line).toBeVisible()
  await expect(page.getByRole('heading', { name: FIXTURE_TITLE })).toBeVisible()
  await expect(banner).toHaveCount(0)
})

test('corrected details persist across a reload, and marking the paper retracted shows the banner', async ({
  page,
  paperId,
}) => {
  const line = await openReader(page, paperId)
  await page.getByRole('button', { name: 'Edit details' }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit details' })
  await dialog.getByLabel('Title').fill('Corrected Fixture Title')
  await dialog.getByLabel('Authors').fill('Ada Lovelace\nAlan Turing')
  await dialog.getByLabel('Year').fill('1843')
  // Owner ruling: the abstract is correctable in this dialog too, locked in manual_fields the same way.
  await dialog.getByLabel('Abstract').fill('A corrected abstract for the fixture paper.')
  await dialog.getByRole('checkbox', { name: 'Retracted' }).check()
  await dialog.getByRole('button', { name: 'Save' }).click()

  await expect(dialog).toBeHidden()
  const heading = page.getByRole('heading', { name: 'Corrected Fixture Title' })
  await expect(heading).toBeVisible()
  await expect(page.locator('.retraction-banner')).toBeVisible()

  await page.reload()
  await expect(line).toBeVisible()
  await expect(heading).toBeVisible()
  await expect(page.locator('.retraction-banner')).toBeVisible()
  await page.getByRole('button', { name: 'Edit details' }).click()
  await expect(dialog.getByLabel('Authors')).toHaveValue('Ada Lovelace\nAlan Turing')
  await expect(dialog.getByLabel('Year')).toHaveValue('1843')
  await expect(dialog.getByLabel('Abstract')).toHaveValue('A corrected abstract for the fixture paper.')
  await expect(dialog.getByRole('button', { name: 'Save' })).toBeDisabled() // nothing changed yet
})

test('a correction the server refuses keeps the dialog open to fix it', async ({ page, request, paperId }) => {
  await openReader(page, paperId)
  await page.getByRole('button', { name: 'Edit details' }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit details' })
  await dialog.getByLabel('DOI').fill('not a doi')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(dialog.getByRole('alert')).toHaveText("not a DOI: 'not a doi'")

  // Still open, with the draft intact: fixing the value is enough.
  const doi = `10.5555/e2e-${paperId}`
  await dialog.getByLabel('DOI').fill(`https://doi.org/${doi}`)
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(dialog).toBeHidden()
  expect((await (await request.get(`/api/papers/${paperId}`)).json()).doi).toBe(doi)
})

test('a 10,000-character abstract keeps Save and Cancel reachable, and still saves', async ({ page, paperId }) => {
  await openReader(page, paperId)
  await page.getByRole('button', { name: 'Edit details' }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit details' })
  const longAbstract = 'a '.repeat(5000) // exactly 10,000 chars, the field's maxLength
  await dialog.getByLabel('Abstract').fill(longAbstract)
  // The dialog scrolls internally now, instead of growing past the viewport with no way to reach the footer.
  const save = dialog.getByRole('button', { name: 'Save' })
  const cancel = dialog.getByRole('button', { name: 'Cancel' })
  await save.scrollIntoViewIfNeeded()
  await expect(save).toBeInViewport()
  await cancel.scrollIntoViewIfNeeded()
  await expect(cancel).toBeInViewport()
  await save.click()
  await expect(dialog).toBeHidden()

  await page.reload()
  await page.getByRole('button', { name: 'Edit details' }).click()
  await expect(dialog.getByLabel('Abstract')).toHaveValue(longAbstract.trim())
})

test('a whitespace-only title disables Save', async ({ page, paperId }) => {
  await openReader(page, paperId)
  await page.getByRole('button', { name: 'Edit details' }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit details' })
  await dialog.getByLabel('Title').fill('   ')
  await expect(dialog.getByRole('button', { name: 'Save' })).toBeDisabled()
})
