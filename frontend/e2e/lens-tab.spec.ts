import { expect, openReader, pickLens, test } from './fixtures'

test('the Lens tab lists the lens, and a role fix stays after a reload until Automatic undoes it', async ({ page, paperId }) => {
  await openReader(page, paperId)
  await page.getByRole('tab', { name: 'Lens' }).click()
  const panel = page.getByRole('complementary', { name: 'Lens' })
  const rows = panel.locator('li.lens-section')
  const method = rows.filter({ hasText: '2 Method' })

  // Full paper lists every section with its role; a row jumps to its passage.
  await expect(panel.getByRole('heading', { name: 'Full paper' })).toBeVisible()
  await expect(rows).toHaveCount(2)
  await expect(rows.nth(0).locator('.role-chip')).toHaveText('Introduction')
  await expect(method.locator('.role-chip')).toHaveText('Method')
  await method.locator('button.lens-jump').click()
  await expect(page.locator('.pdf-page[data-page="2"] .chunk-flash').first()).toBeInViewport()

  // Key ideas lists the introduction only.
  await pickLens(page, 'Key ideas')
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toContainText('1 Introduction')

  // Fix "2 Method" as the conclusion, from Full paper, which lists it.
  await pickLens(page, 'Full paper')
  await panel.getByRole('button', { name: 'Section actions for 2 Method' }).click()
  await page.getByRole('menuitemradio', { name: 'Conclusion' }).click()
  await expect(method.locator('.role-chip')).toHaveText('Conclusion')
  await expect(method.locator('.role-fixed')).toHaveText('fixed by you')

  // It is kept: after a reload (the hash keeps the tab; the lens starts on Full paper again) it is in Key ideas.
  await page.reload()
  await expect(method.locator('.role-chip')).toHaveText('Conclusion')
  await pickLens(page, 'Key ideas')
  await expect(rows).toHaveCount(2)
  await expect(page.locator('.lens-fade')).toHaveCount(0)

  // Automatic undoes the fix.
  await pickLens(page, 'Full paper')
  await panel.getByRole('button', { name: 'Section actions for 2 Method' }).click()
  await page.getByRole('menuitemradio', { name: 'Automatic' }).click()
  await expect(method.locator('.role-chip')).toHaveText('Method')
  await expect(method.locator('.role-fixed')).toHaveCount(0)
})

test('a lens says when the paper has no sections for it, or no limitations section', async ({ page, paperId }) => {
  await openReader(page, paperId)
  await page.getByRole('tab', { name: 'Lens' }).click()
  const panel = page.getByRole('complementary', { name: 'Lens' })

  await pickLens(page, 'Related work')
  await expect(panel.locator('.lens-notice')).toHaveText(
    "This paper has no sections for Related work. Switch to Full paper to fix a section's role.",
  )
  await expect(panel.locator('li.lens-section')).toHaveCount(0)
  await expect(page.locator('.lens-step')).toHaveCount(0)

  await pickLens(page, 'Critical check')
  await expect(panel.locator('.lens-notice')).toHaveText('No limitations section found in this paper.')
  await expect(panel.locator('li.lens-section')).toHaveCount(1)
})

test('at the narrowest panel the Lens tab is in view when it is the active tab', async ({ page, paperId }) => {
  await page.addInitScript(() => window.localStorage.setItem('paperlab-panel-width', '320'))
  await openReader(page, paperId)
  const panel = page.locator('.reader-panel')
  const lensTab = panel.getByRole('tab', { name: 'Lens' })

  // Seven tabs in 320 px: they fit, or the tab list scrolls sideways and brings the active tab into view (R4).
  await page.evaluate((id) => {
    window.location.hash = `#/papers/${id}?tab=lens`
  }, paperId)
  await expect(lensTab).toHaveAttribute('data-state', 'active')
  const panelBox = await panel.boundingBox()
  expect(Math.round(panelBox!.width)).toBe(320)
  await expect
    .poll(async () => {
      const tabBox = await lensTab.boundingBox()
      return tabBox!.x >= panelBox!.x && tabBox!.x + tabBox!.width <= panelBox!.x + panelBox!.width
    })
    .toBe(true)
})
