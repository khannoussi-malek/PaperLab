import { FIXTURE_TITLE, expect, openReader, test, type Rect } from './fixtures'

const LETTER_WIDTH_PT = 612

test('renders every page with ink, and the text layer sits on PyMuPDF’s chunk at each zoom', async ({
  page,
  request,
  paperId,
}) => {
  const line = await openReader(page, paperId)
  await expect(page.getByRole('heading', { name: FIXTURE_TITLE })).toBeVisible()
  await expect(page.locator('.pdf-page')).toHaveCount(2)

  const firstPage = page.locator('.pdf-page[data-page="1"]')
  // A correctly sized but blank canvas would pass every other check, so count dark pixels.
  await expect
    .poll(() =>
      firstPage.locator('canvas').evaluate((canvas: HTMLCanvasElement) => {
        const { data } = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height)
        let dark = 0
        for (let i = 0; i < data.length; i += 4) if (data[i + 3] > 0 && data[i] < 128) dark++
        return dark
      }),
    )
    .toBeGreaterThan(100)

  const [chunk] = await (await request.get(`/api/papers/${paperId}/chunks?page=1`)).json()
  const [x0, y0, x1, y1] = chunk.bbox[0] as Rect
  const tolerance = 4

  for (const [zoomLabel, scale] of [['150%', 1.5], ['200%', 2], ['125%', 1.25]] as const) {
    if (zoomLabel === '200%') await page.getByRole('button', { name: 'Zoom in' }).click()
    if (zoomLabel === '125%') {
      await page.getByRole('button', { name: 'Zoom out' }).click()
      await page.getByRole('button', { name: 'Zoom out' }).click()
    }
    await expect(page.locator('.zoom-level')).toHaveText(zoomLabel)
    await expect.poll(async () => (await firstPage.boundingBox())?.width).toBeCloseTo(LETTER_WIDTH_PT * scale, 0)

    await expect
      .poll(async () => {
        const pageBox = (await firstPage.boundingBox())!
        const lineBox = await line.boundingBox()
        if (!lineBox) return false
        return (
          lineBox.x >= pageBox.x + x0 * scale - tolerance &&
          lineBox.y >= pageBox.y + y0 * scale - tolerance &&
          lineBox.x + lineBox.width <= pageBox.x + x1 * scale + tolerance &&
          lineBox.y + lineBox.height <= pageBox.y + y1 * scale + tolerance
        )
      })
      .toBe(true)
  }

  await page.getByRole('link', { name: '← Library' }).click()
  await expect(page.getByRole('heading', { name: 'PaperLab' })).toBeVisible()
})

test('a missing paper shows an error instead of a blank reader', async ({ page }) => {
  await page.goto('/#/papers/00000000-0000-0000-0000-000000000000')
  await expect(page.getByRole('alert')).toBeVisible()
})
