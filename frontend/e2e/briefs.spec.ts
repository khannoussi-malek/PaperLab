import { expect, openReader, pickLens, test } from './fixtures'

test('a Key ideas brief is AI, cites its passage, and goes out of date when a role changes', async ({ page, paperId }) => {
  await openReader(page, paperId)
  await page.getByRole('tab', { name: 'Lens' }).click()
  const panel = page.getByRole('complementary', { name: 'Lens' })
  const card = panel.locator('.brief-card')

  await pickLens(page, 'Key ideas')
  await card.getByRole('button', { name: 'Generate brief' }).click()

  // The fake model's answer, labelled AI with the model that wrote it.
  await expect(card.locator('.brief-text')).toHaveText('Fake answer: the method is described here [C1].')
  await expect(card.locator('.provenance-badge')).toHaveText('AI')
  await expect(card.locator('.brief-meta')).toContainText('fake:')
  await expect(card.locator('.brief-stale')).toHaveCount(0)
  await card.locator('.brief-cite', { hasText: '[C1]' }).click()
  await expect(page.locator('.pdf-page[data-page="1"] .chunk-flash').first()).toBeInViewport()

  // "2 Method" becomes a conclusion, so Key ideas gains a passage and the brief is out of date.
  await pickLens(page, 'Full paper')
  await panel.getByRole('button', { name: 'Section actions for 2 Method' }).click()
  await page.getByRole('menuitemradio', { name: 'Conclusion' }).click()
  await expect(panel.locator('li.lens-section', { hasText: '2 Method' }).locator('.role-chip')).toHaveText('Conclusion')
  await pickLens(page, 'Key ideas')
  await expect(card.locator('.brief-stale')).toContainText('Out of date: sections changed')

  // Wait for the briefs to be read again (the stream's `done` refetches them), so the checks below see the saved brief,
  // not the old stale one that is still on screen when the click returns. (A streamed POST's `finished()` never
  // resolved here, so the re-read is the signal.)
  const reread = page.waitForResponse((r) => r.request().method() === 'GET' && /\/briefs$/.test(new URL(r.url()).pathname))
  await card.getByRole('button', { name: 'Regenerate' }).click()
  await reread
  await expect(card.locator('.brief-meta')).toContainText('fake:')
  await expect(card.locator('.brief-stale')).toHaveCount(0)
  await expect(card.locator('.brief-text')).toHaveText('Fake answer: the method is described here [C1].')
})
