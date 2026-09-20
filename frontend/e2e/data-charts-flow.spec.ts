import { dragBox, expect, openReader, selectSubstring, TABLE_LINE, test } from './fixtures'

test('capture, add a number, add own data, chart all three, fix a cell, open the source, note it, rename, duplicate, edit, dark mode', async ({
  page,
  request,
  tablePaperId,
  dataName,
}) => {
  test.setTimeout(180_000)

  // 1. Draw a box over the table, fix one cell, save.
  const line = await openReader(page, tablePaperId, TABLE_LINE)
  await page.getByRole('button', { name: 'Capture table' }).click()
  await dragBox(page, 1, [60, 145, 420, 200])
  const capture = page.getByRole('dialog', { name: 'Capture table' })
  await capture.getByRole('textbox', { name: 'Table name' }).fill(`${dataName} table`)
  // The header row already names the columns, so row 2 is the second data row without promoting anything.
  await capture.getByRole('textbox', { name: 'Row 2, column 2' }).fill('90.8')
  await capture.getByRole('button', { name: 'Save table' }).click()
  await expect(page.locator('.pdf-page[data-page="1"] .table-region')).toHaveCount(1)
  const tableCard = page.locator('article.dataset-card', { hasText: `${dataName} table` })
  const tableId = await tableCard.getAttribute('data-dataset-id')

  // 2. Select "88.5 ± 0.3 F1" and add it as a number.
  await selectSubstring(line, '88.5 ± 0.3 F1')
  await page.getByRole('button', { name: 'Add as number' }).click()
  const number = page.getByRole('dialog', { name: 'Add as number' })
  await number.getByRole('textbox', { name: 'Label' }).fill('XLNet-ish')
  await number.getByRole('button', { name: 'Add number' }).click()
  await page.getByRole('tab', { name: 'Data' }).click()
  const numbersCard = page.locator('article.dataset-card', { hasText: '1 number' })
  await expect(numbersCard).toBeVisible()
  const numbersId = await numbersCard.getAttribute('data-dataset-id')
  const saved = await (await request.get(`/api/datasets/${numbersId}`)).json()
  expect(saved.rows[0].cells.find((c: { value: number | null }) => c.value !== null)).toMatchObject({ value: 88.5, error: 0.3 })

  // 3. Upload a CSV as your own data.
  await page.goto('/#/charts')
  await page.getByRole('button', { name: 'New dataset' }).click()
  const upload = page.getByRole('dialog', { name: 'New dataset' })
  await upload.getByRole('textbox', { name: 'Dataset name' }).fill(`${dataName} runs`)
  await upload.getByRole('tab', { name: 'Upload CSV' }).click()
  await upload.getByLabel('CSV file').setInputFiles({ name: 'runs.csv', mimeType: 'text/csv', buffer: Buffer.from('System,Dev F1\nmine,92.0\n') })
  await upload.getByRole('button', { name: 'Create dataset' }).click()
  await expect(page.getByRole('heading', { name: `${dataName} runs` })).toBeVisible()
  const runsId = page.url().match(/datasets\/([0-9a-f-]{36})/)![1]

  // 4. Build a bar chart from all three; the preview shows 3 series; save and reopen.
  await page.goto('/#/charts/new')
  for (const id of [tableId, numbersId, runsId]) {
    await page.getByRole('button', { name: 'Add series' }).click()
    await page.getByRole('dialog', { name: 'Choose data' }).locator(`[data-dataset-id="${id}"]`).click()
  }
  await expect(page.locator('.chart-view')).toHaveAttribute('data-series-count', '3')
  await page.getByRole('textbox', { name: 'Chart title' }).fill(`${dataName} chart`)
  await page.getByRole('button', { name: 'Save chart' }).click()
  await expect(page.getByRole('heading', { name: `${dataName} chart` })).toBeVisible()
  const chartUrl = page.url()
  const chartId = chartUrl.match(/charts\/([0-9a-f-]{36})/)![1]
  await page.reload()
  await expect(page.locator('.chart-view')).toHaveAttribute('data-series-count', '3')

  // 5. Fix a cell in the table: the reopened chart shows the new value.
  await page.goto(`/#/datasets/${tableId}`)
  await page.getByRole('textbox', { name: 'Row 1, column 2' }).fill('88.6')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByRole('button', { name: 'Save' })).toBeDisabled()
  await page.goto(chartUrl)
  await page.getByRole('button', { name: 'View data table' }).click()
  await expect(page.getByRole('table', { name: 'Chart data' })).toContainText('88.6 (edited)')

  // 6. Click BERT-L's bar: the reader opens on page 1 with that cell flashed.
  await page.getByRole('button', { name: 'View data table' }).click()
  const bars = page.locator('.chart-view .barlayer .trace').first().locator('.point path')
  const box = await bars.nth(1).boundingBox()
  await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height - 4)
  await expect(page).toHaveURL(new RegExp(`#/papers/${tablePaperId}\\?tab=data$`))
  await expect(page.locator('.pdf-page[data-page="1"] .chunk-flash')).toHaveCount(1)

  // 7. Add to note: the note appears in the source paper's notes panel with the chart inside.
  await page.goto(chartUrl)
  await page.getByRole('button', { name: 'Chart actions' }).click()
  await page.getByRole('menuitem', { name: 'Add to note…' }).click()
  await page.getByRole('status').filter({ hasText: 'Added to a note in 1 paper.' }).getByRole('link', { name: 'Open the note' }).click()
  const embed = page.locator(`article.note .note-chart[data-chart-id="${chartId}"]`)
  await expect(embed.locator('.chart-view')).toHaveAttribute('data-chart-type', 'bar')

  // 8. Rename the chart inline: the new title shows after reload.
  await page.goto(chartUrl)
  await page.getByRole('button', { name: 'Chart actions' }).click()
  await page.getByRole('menuitem', { name: 'Rename' }).click()
  await page.getByRole('textbox', { name: 'Chart title' }).fill(`${dataName} chart v2`)
  await page.keyboard.press('Enter')
  // The heading comes back once the rename is saved; reloading before then could cancel it.
  await expect(page.getByRole('heading', { name: `${dataName} chart v2` })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: `${dataName} chart v2` })).toBeVisible()

  // 9. Duplicate, then change the copy to a line chart: the original and the note stay a bar chart.
  await page.getByRole('button', { name: 'Chart actions' }).click()
  await page.getByRole('menuitem', { name: 'Duplicate' }).click()
  await expect(page.getByRole('heading', { name: `${dataName} chart v2 (copy)` })).toBeVisible()
  await page.getByRole('link', { name: 'Edit' }).click()
  await page.getByRole('radio', { name: 'Line', exact: true }).click()
  await page.getByRole('button', { name: 'Save changes' }).click()
  // The builder's preview already shows the new type, so wait for the save to land on the chart page.
  await expect(page).toHaveURL(/#\/charts\/[0-9a-f-]{36}$/)
  await expect(page.locator('.chart-view')).toHaveAttribute('data-chart-type', 'line')
  expect((await (await request.get(`/api/charts/${chartId}`)).json()).spec.type).toBe('bar')
  await openReader(page, tablePaperId, TABLE_LINE)
  await expect(embed.locator('.chart-view')).toHaveAttribute('data-chart-type', 'bar')

  // 10. Edit the original: the builder says it is used in 1 note, and after saving the note shows the change.
  await page.goto(`/#/charts/${chartId}/edit`)
  await expect(page.getByText('Used in 1 note, which will show this change')).toBeVisible()
  await page.getByRole('radio', { name: 'Scatter', exact: true }).click()
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page).toHaveURL(chartUrl)
  await expect(page.locator('.chart-view')).toHaveAttribute('data-chart-type', 'scatter')
  await openReader(page, tablePaperId, TABLE_LINE)
  await expect(embed.locator('.chart-view')).toHaveAttribute('data-chart-type', 'scatter')

  // 11. Dark mode draws the chart, and the data table lists the values.
  await page.goto(`/#/charts/${chartId}`)
  await page.getByRole('button', { name: 'Toggle theme' }).click()
  await page.getByRole('menuitem', { name: 'Dark' }).click()
  await expect(page.locator('html')).toHaveClass(/\bdark\b/)
  await expect(page.locator('.chart-view .scatterlayer .point').first()).toBeVisible()
  await page.getByRole('button', { name: 'View data table' }).click()
  const numbers = page.getByRole('table', { name: 'Chart data' })
  for (const value of ['88.6 (edited)', '90.8 (edited)', '88.5 ± 0.3', '92.0']) await expect(numbers).toContainText(value)
})
