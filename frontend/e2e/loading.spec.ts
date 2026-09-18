import type { Locator, Page } from '@playwright/test'
import { FIRST_LINE, addOwnData, expect, test } from './fixtures'

const firstLine = (page: Page) => page.locator('.pdf-page[data-page="1"] .textLayer span', { hasText: FIRST_LINE })

/** Plotly's chunk, in the dev server and in a build alike. */
const PLOTLY = /plotly/

/** Opens a hash in the same document, the way a link does: `page.goto` would reload and start everything afresh. */
const follow = (page: Page, hash: string) => page.evaluate((to) => (window.location.hash = to), hash)

test('one PDF.js worker serves the library preview and every paper opened after it', async ({
  page,
  paperId,
  secondPaperId,
}) => {
  const pdfWorkers: string[] = []
  page.on('worker', (worker) => {
    if (worker.url().includes('pdf.worker')) pdfWorkers.push(worker.url())
  })

  await page.goto('/')
  await expect(page.locator('.paper-preview canvas')).toBeVisible()
  for (const id of [paperId, secondPaperId, paperId]) {
    await follow(page, `#/papers/${id}`)
    await expect(firstLine(page)).toBeVisible()
  }
  expect(pdfWorkers).toHaveLength(1)
})

test('the chart library starts loading as the Charts list opens, before any chart is clicked', async ({ page }) => {
  const plotly = page.waitForRequest(PLOTLY)
  await page.goto('/#/charts')
  await plotly
})

test('pointing at a link into a chart starts loading the chart library; the page alone does not', async ({
  page,
  request,
  dataName,
}) => {
  const dataset = await addOwnData(request, dataName, 'x,y\n1,2\n3,4\n')
  const requested: string[] = []
  page.on('request', (r) => {
    if (PLOTLY.test(r.url())) requested.push(r.url())
  })
  await page.goto(`/#/datasets/${dataset.id}`)
  const quickChart = page.getByRole('link', { name: 'Quick chart' })
  await expect(quickChart).toBeVisible()
  await page.waitForTimeout(500)
  expect(requested).toEqual([])

  const plotly = page.waitForRequest(PLOTLY)
  await quickChart.hover()
  await plotly
})

/** Holds GET responses matching `glob` back for a second, so what the page shows while it waits stays on screen. */
const slow = (page: Page, glob: string) =>
  page.route(glob, async (route) => {
    if (route.request().method() === 'GET') await new Promise((resolve) => setTimeout(resolve, 1000))
    await route.fallback()
  })

const animationOf = (locator: Locator) =>
  locator.evaluate((element) => {
    const style = getComputedStyle(element)
    return { name: style.animationName, delay: style.animationDelay }
  })

test.describe('loading placeholders', () => {
  test.use({ reducedMotion: 'no-preference' })

  test('stay hidden for their first 150 ms, so a fast load never flashes them', async ({ page, paperId }) => {
    await slow(page, '**/api/papers')
    await page.goto('/')
    const list = page.getByText('Loading…', { exact: true }).first()
    await expect(list).toBeVisible()
    expect(await animationOf(list)).toEqual({ name: 'enter', delay: '0.15s' })

    await slow(page, `**/api/papers/${paperId}`)
    await follow(page, `#/papers/${paperId}`)
    const title = page.getByRole('heading', { level: 1 }).getByText('Loading…')
    await expect(title).toBeVisible()
    expect(await animationOf(title)).toEqual({ name: 'enter', delay: '0.15s' })
  })
})

test.describe('loading placeholders with the OS set to reduce motion', () => {
  test.use({ reducedMotion: 'reduce' })

  test('show at once', async ({ page }) => {
    await slow(page, '**/api/papers')
    await page.goto('/')
    const list = page.getByText('Loading…', { exact: true }).first()
    await expect(list).toBeVisible()
    expect((await animationOf(list)).name).toBe('none')
  })
})
