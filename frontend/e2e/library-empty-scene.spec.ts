import { expect, test } from './fixtures'

test('the empty Library draws its 3D page when the browser can, and keeps its words either way', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  await page.route('**/api/papers', (route) => (route.request().method() === 'GET' ? route.fulfill({ json: [] }) : route.fallback()))
  await page.goto('/')
  await expect(page.getByText('No papers yet. Upload a PDF to start.')).toBeVisible()
  const webgl = await page.evaluate(() => document.createElement('canvas').getContext('webgl2') !== null)
  const canvas = page.locator('canvas[aria-hidden="true"]')
  if (webgl) await expect(canvas).toBeVisible() // hidden until the director runs, so this proves it drew
  else await expect(canvas).toHaveCount(0)
  expect(errors).toEqual([])
})
