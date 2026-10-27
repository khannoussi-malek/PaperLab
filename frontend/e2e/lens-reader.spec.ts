import type { Locator } from '@playwright/test'
import { expect, LONG_FIRST_LINE, openReader, pickLens, test } from './fixtures'

/** Whether two rendered elements' boxes overlap. */
async function overlap(a: Locator, b: Locator): Promise<boolean> {
  const [boxA, boxB] = [await a.boundingBox(), await b.boundingBox()]
  if (!boxA || !boxB) throw new Error('both elements must be rendered')
  return (
    boxA.x < boxB.x + boxB.width && boxB.x < boxA.x + boxA.width && boxA.y < boxB.y + boxB.height && boxB.y < boxA.y + boxA.height
  )
}

test('Key ideas fades the method, keeps its heading readable, and opens on the introduction', async ({ page, paperId }) => {
  await openReader(page, paperId)

  await pickLens(page, 'Key ideas')

  // The fixture: "1 Introduction" on page 1 is the lens; "2 Method" on page 2 isn't.
  await expect(page.locator('.lens-step')).toHaveText('1/1')
  await expect(page.locator('.pdf-page[data-page="1"] .chunk-flash').first()).toBeInViewport()
  await expect(page.locator('.pdf-page[data-page="1"] .lens-fade')).toHaveCount(0)
  const fade = page.locator('.pdf-page[data-page="2"] .lens-fade')
  await expect(fade).toHaveCount(1)
  // D122: a heading is no chunk's rect, so no fade covers it; the method's own text is under the fade.
  const heading = page.locator('.pdf-page[data-page="2"] .textLayer span', { hasText: '2 Method' })
  const body = page.locator('.pdf-page[data-page="2"] .textLayer span', { hasText: 'The second page describes' })
  await heading.scrollIntoViewIfNeeded()
  await expect(heading).toBeVisible()
  expect(await overlap(heading, fade)).toBe(false)
  expect(await overlap(body, fade)).toBe(true)

  await pickLens(page, 'Full paper')
  await expect(page.locator('.lens-fade')).toHaveCount(0)
  await expect(page.locator('.lens-step')).toHaveCount(0)
})

test('the arrows step through a lens one run at a time', async ({ page, request, longPaperId }) => {
  // Two separate runs in Key ideas: page 1 as the introduction and page 6 as the conclusion.
  for (const [title, role] of [
    ['1 On retrieval', 'intro'],
    ['6 On workspaces', 'conclusion'],
  ] as const) {
    const fixed = await request.put(`/api/papers/${longPaperId}/section-roles`, { data: { section_title: title, role } })
    expect(fixed.status()).toBe(200)
  }
  await openReader(page, longPaperId, LONG_FIRST_LINE)
  const previous = page.getByRole('button', { name: 'Previous lens section' })
  const next = page.getByRole('button', { name: 'Next lens section' })

  await pickLens(page, 'Key ideas')
  await expect(page.locator('.lens-step')).toHaveText('1/2')
  await expect(previous).toBeDisabled()

  await next.click()
  await expect(page.locator('.lens-step')).toHaveText('2/2')
  await expect(page.locator('.pdf-page[data-page="6"] .chunk-flash').first()).toBeInViewport()
  await expect(next).toBeDisabled()

  await previous.click()
  await expect(page.locator('.lens-step')).toHaveText('1/2')
  await expect(page.locator('.pdf-page[data-page="1"] .chunk-flash').first()).toBeInViewport()
})
