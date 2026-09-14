import type { Page } from '@playwright/test'
import { expect, openReader, test } from './fixtures'

const VIEWPORT = { width: 1400, height: 900 }

const panelBox = async (page: Page) => (await page.locator('.reader-panel').boundingBox())!

/** Presses on the panel's left edge (where the handle straddles the border) and drags it to `toX`. */
async function dragEdgeTo(page: Page, toX: number) {
  const box = await panelBox(page)
  const y = box.y + box.height / 2
  await page.mouse.move(box.x, y)
  await page.mouse.down()
  await page.mouse.move(toX, y, { steps: 5 })
  await page.mouse.up()
}

test('the side panel resizes by drag and keyboard, stays within bounds, and keeps its width across a reload', async ({
  page,
  paperId,
}) => {
  await page.setViewportSize(VIEWPORT)
  await openReader(page, paperId)
  const handle = page.getByRole('separator', { name: 'Resize panel' })
  await expect.poll(async () => (await panelBox(page)).width).toBe(360)

  await dragEdgeTo(page, VIEWPORT.width - 560)
  await expect.poll(async () => (await panelBox(page)).width).toBe(560)
  await expect(handle).toHaveAttribute('aria-valuenow', '560')

  await page.reload()
  await expect.poll(async () => (await panelBox(page)).width).toBe(560)

  // The panel is on the right, so ArrowRight moves its edge right: narrower.
  await handle.focus()
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('ArrowRight')
  await expect.poll(async () => (await panelBox(page)).width).toBe(528)

  await dragEdgeTo(page, VIEWPORT.width - 1)
  await expect.poll(async () => (await panelBox(page)).width).toBe(320)
  await dragEdgeTo(page, 0)
  await expect.poll(async () => (await panelBox(page)).width).toBe(840) // 60% of the window

  await handle.dblclick()
  await expect.poll(async () => (await panelBox(page)).width).toBe(360)
})
