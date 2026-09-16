import { addChart, addOwnData, barSpec, expect, test } from './fixtures'

test('uploading a CSV makes your own data, listed under My data', async ({ page, dataName }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'Charts' }).click()
  await expect(page.getByRole('heading', { name: 'Charts', level: 1 })).toBeVisible()
  await page.getByRole('link', { name: '← Library' }).click()
  await expect(page.getByRole('heading', { name: 'PaperLab', level: 1 })).toBeVisible()
  await page.getByRole('link', { name: 'Charts' }).click()

  await page.getByRole('button', { name: 'New dataset' }).click()
  const dialog = page.getByRole('dialog', { name: 'New dataset' })
  await dialog.getByRole('textbox', { name: 'Dataset name' }).fill(`${dataName} runs`)
  await dialog.getByRole('tab', { name: 'Upload CSV' }).click()
  await dialog.getByLabel('CSV file').setInputFiles({ name: 'runs.csv', mimeType: 'text/csv', buffer: Buffer.from('run,F1\nmine,92.0\nbaseline,89.1\n') })
  await dialog.getByRole('button', { name: 'Create dataset' }).click()

  await expect(page.getByRole('heading', { name: `${dataName} runs` })).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Row 1, column 2' })).toHaveValue('92.0')
  await page.goto('/#/charts')
  await expect(page.locator('a.own-dataset', { hasText: `${dataName} runs` })).toContainText('2 rows × 2 columns')
})

test('pasted spreadsheet text becomes a dataset, and a typed one starts as an empty grid', async ({ page, dataName }) => {
  await page.goto('/#/charts')
  await page.getByRole('button', { name: 'New dataset' }).click()
  let dialog = page.getByRole('dialog', { name: 'New dataset' })
  await dialog.getByRole('textbox', { name: 'Dataset name' }).fill(`${dataName} pasted`)
  await dialog.getByRole('tab', { name: 'Paste' }).click()
  await dialog.getByRole('textbox', { name: 'Pasted data' }).fill('model\tscore\nA\t1.5\nB\t2.5')
  await dialog.getByRole('button', { name: 'Create dataset' }).click()
  await expect(page.getByRole('textbox', { name: 'Column 2 name' })).toHaveValue('score')

  await page.goto('/#/charts')
  await page.getByRole('button', { name: 'New dataset' }).click()
  dialog = page.getByRole('dialog', { name: 'New dataset' })
  await dialog.getByRole('textbox', { name: 'Dataset name' }).fill(`${dataName} typed`)
  await dialog.getByRole('button', { name: 'Create dataset' }).click()
  await expect(page.getByRole('textbox', { name: 'Column 1 name' })).toHaveValue('Column 1')
  await expect(page.getByRole('textbox', { name: 'Row 3, column 2' })).toHaveValue('')
})

test('a chart is renamed inline, duplicated, and the copy deleted, from the list', async ({ page, request, dataName }) => {
  const data = await addOwnData(request, `${dataName} runs`, 'run,F1\nmine,92.0\n')
  await addChart(request, `${dataName} chart`, barSpec(data, 'run', ['F1']))
  await page.goto('/#/charts')

  const row = page.locator('.chart-row', { hasText: `${dataName} chart` })
  await expect(row).toContainText('My data')
  await row.getByRole('button', { name: 'Chart actions' }).click()
  await page.getByRole('menuitem', { name: 'Rename' }).click()
  await row.getByRole('textbox', { name: 'Chart title' }).fill(`${dataName} renamed`)
  await page.keyboard.press('Enter')
  await page.reload()
  const renamed = page.locator('.chart-row', { hasText: `${dataName} renamed` })
  await expect(renamed).toHaveCount(1)

  await renamed.getByRole('button', { name: 'Chart actions' }).click()
  await page.getByRole('menuitem', { name: 'Duplicate' }).click()
  const copy = page.locator('.chart-row', { hasText: `${dataName} renamed (copy)` })
  await expect(copy).toHaveCount(1)

  page.once('dialog', (confirm) => void confirm.accept())
  await copy.getByRole('button', { name: 'Chart actions' }).click()
  await page.getByRole('menuitem', { name: 'Delete' }).click()
  await expect(copy).toHaveCount(0)
  await expect(page.locator('.chart-row', { hasText: `${dataName} renamed` })).toHaveCount(1)
})

test('renaming from the menu keeps focus on the input, so typed keystrokes land there', async ({ page, request, dataName }) => {
  const data = await addOwnData(request, `${dataName} runs`, 'run,F1\nmine,92.0\n')
  await addChart(request, `${dataName} chart`, barSpec(data, 'run', ['F1']))
  await page.goto('/#/charts')

  const row = page.locator('.chart-row', { hasText: `${dataName} chart` })
  await row.getByRole('button', { name: 'Chart actions' }).click()
  await page.getByRole('menuitem', { name: 'Rename' }).click()
  const input = row.getByRole('textbox', { name: 'Chart title' })

  // Radix hands focus back to the still-mounted "Chart actions" trigger once its close animation finishes
  // (~100ms) unless that's suppressed; wait past it so a regression here shows up as keystrokes landing on the
  // button (which would reopen the menu on Enter) instead of the input.
  await page.waitForTimeout(300)
  await expect(input).toBeFocused()
  await page.keyboard.press('Control+a')
  await page.keyboard.type(`${dataName} typed rename`)
  await page.keyboard.press('Enter')

  await expect(page.locator('.chart-row', { hasText: `${dataName} typed rename` })).toHaveCount(1)
})

test('the chart page has a standalone Edit link, and its own menu has no Edit item', async ({ page, request, dataName }) => {
  const data = await addOwnData(request, `${dataName} runs`, 'run,F1\nmine,92.0\n')
  const chart = await addChart(request, `${dataName} chart`, barSpec(data, 'run', ['F1']))
  await page.goto(`/#/charts/${chart.id}`)

  await expect(page.getByRole('link', { name: 'Edit' })).toHaveAttribute('href', `#/charts/${chart.id}/edit`)
  await page.getByRole('button', { name: 'Chart actions' }).click()
  await expect(page.getByRole('menuitem', { name: 'Rename' })).toBeVisible()
  await expect(page.getByRole('menuitem', { name: 'Edit' })).toHaveCount(0)
})

test('My data that fails to load says why and retries, instead of looking empty', async ({ page }) => {
  let fail = true
  await page.route('**/api/datasets', (route) =>
    fail ? route.fulfill({ status: 500, json: { detail: 'Datasets are unavailable' } }) : route.continue(),
  )
  await page.goto('/#/charts')
  await expect(page.getByText('Datasets are unavailable')).toBeVisible()
  await expect(page.getByText('No datasets of your own yet.')).toHaveCount(0)

  fail = false
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByText('Datasets are unavailable')).toHaveCount(0)
})

test('a Duplicate or Delete the server refuses says why, on the list and on the chart page', async ({ page, request, dataName }) => {
  const data = await addOwnData(request, `${dataName} runs`, 'run,F1\nmine,92.0\n')
  const chart = await addChart(request, `${dataName} chart`, barSpec(data, 'run', ['F1']))
  await page.route(`**/api/charts/${chart.id}/duplicate`, (route) =>
    route.fulfill({ status: 500, json: { detail: 'Duplicating failed on the server' } }),
  )
  await page.route(`**/api/charts/${chart.id}`, (route) =>
    route.request().method() === 'DELETE' ? route.fulfill({ status: 500, json: { detail: 'Deleting failed on the server' } }) : route.continue(),
  )
  page.on('dialog', (confirm) => void confirm.accept())

  await page.goto('/#/charts')
  const row = page.locator('.chart-row', { hasText: `${dataName} chart` })
  await row.getByRole('button', { name: 'Chart actions' }).click()
  await page.getByRole('menuitem', { name: 'Duplicate' }).click()
  await expect(page.getByText('Duplicating failed on the server')).toBeVisible()
  await row.getByRole('button', { name: 'Chart actions' }).click()
  await page.getByRole('menuitem', { name: 'Delete' }).click()
  await expect(page.getByText('Deleting failed on the server')).toBeVisible()
  await expect(row).toHaveCount(1)

  await page.goto(`/#/charts/${chart.id}`)
  await page.getByRole('button', { name: 'Chart actions' }).click()
  await page.getByRole('menuitem', { name: 'Delete' }).click()
  await expect(page.getByText('Deleting failed on the server')).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`#/charts/${chart.id}$`))
})

test("a chart whose refetch fails keeps its drawing and never claims it doesn't exist", async ({ page, request, dataName }) => {
  const data = await addOwnData(request, `${dataName} runs`, 'run,F1\nmine,92.0\n')
  const chart = await addChart(request, `${dataName} chart`, barSpec(data, 'run', ['F1']))
  await page.goto(`/#/charts/${chart.id}`)
  await expect(page.locator('.chart-view')).toHaveAttribute('data-series-count', '1')

  await page.route(`**/api/charts/${chart.id}`, (route) =>
    route.request().method() === 'GET' ? route.fulfill({ status: 500, json: { detail: 'Server hiccup' } }) : route.continue(),
  )
  const failedRefetch = page.waitForResponse((response) => response.url().endsWith(`/api/charts/${chart.id}`) && response.status() === 500)
  await page.getByRole('button', { name: 'Chart actions' }).click()
  await page.getByRole('menuitem', { name: 'Rename' }).click()
  await page.getByRole('textbox', { name: 'Chart title' }).fill(`${dataName} renamed`)
  await page.keyboard.press('Enter')
  await failedRefetch

  await expect(page.locator('.chart-view')).toHaveAttribute('data-series-count', '1')
  await expect(page.getByText("This chart doesn't exist.")).toHaveCount(0)
})
