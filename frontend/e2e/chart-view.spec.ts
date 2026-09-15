import { addChart, addTable, barSpec, clickBar, expect, test } from './fixtures'

test("a saved chart draws its series and lists its numbers, and a bar opens that cell's spot in the paper", async ({
  page,
  request,
  paperId,
  dataName,
}) => {
  // Cells on page 1, row by row: BERT-L's F1 cell is at [222, 138, 300, 148].
  const table = await addTable(request, paperId, 1, `${dataName} table`, [
    ['System', 'F1'],
    ['BERT-B', '88.5'],
    ['BERT-L', '90.9'],
  ])
  const chart = await addChart(request, `${dataName} chart`, barSpec(table, 'System', ['F1']))

  await page.goto(`/#/charts/${chart.id}`)
  await expect(page.getByRole('heading', { name: `${dataName} chart` })).toBeVisible()
  const view = page.locator('.chart-view')
  await expect(view).toHaveAttribute('data-chart-type', 'bar')
  await expect(view).toHaveAttribute('data-series-count', '1')
  await expect(view.locator('.barlayer .point path')).toHaveCount(2)

  await page.getByRole('button', { name: 'View data table' }).click()
  const numbers = page.getByRole('table', { name: 'Chart data' })
  await expect(numbers.getByRole('row')).toHaveCount(3)
  await expect(numbers.getByRole('row').nth(2)).toContainText('BERT-L90.9')

  await clickBar(page, 1)
  await expect(page).toHaveURL(new RegExp(`#/papers/${paperId}\\?tab=data$`))
  await expect(page.getByRole('tab', { name: 'Data' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.pdf-page[data-page="1"] .chunk-flash')).toHaveCount(1)
})

test('a chart whose data was deleted says so, and the chart redraws in the dark palette', async ({ page, request, paperId, dataName }) => {
  const table = await addTable(request, paperId, 1, `${dataName} table`, [
    ['System', 'F1', 'EM'],
    ['BERT-B', '88.5', '80.8'],
  ])
  const chart = await addChart(request, `${dataName} chart`, barSpec(table, 'System', ['F1', 'EM']))
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto(`/#/charts/${chart.id}`)
  const firstBar = page.locator('.chart-view .barlayer .point path').first()
  await expect(firstBar).toHaveCSS('fill', 'rgb(42, 120, 214)')

  await page.getByRole('button', { name: 'Toggle theme' }).click()
  await page.getByRole('menuitem', { name: 'Dark' }).click()
  await expect(firstBar).toHaveCSS('fill', 'rgb(57, 135, 229)')

  // Remove the EM column with the owner's go-ahead: the chart keeps F1 and warns about the lost series.
  const dataset = await (await request.get(`/api/datasets/${table.id}`)).json()
  const grid = {
    columns: dataset.columns.filter((c: { name: string }) => c.name !== 'EM').map((c: { id: string; name: string }) => ({ id: c.id, name: c.name })),
    rows: dataset.rows.map((row: { id: string; cells: { column_id: string; raw: string }[] }) => ({
      id: row.id,
      cells: row.cells.filter((cell) => cell.column_id !== table.columns[2].id).map((cell) => ({ raw: cell.raw, extracted: cell.raw })),
    })),
  }
  expect((await request.put(`/api/datasets/${table.id}/grid?force=true`, { data: grid })).status()).toBe(200)
  await page.reload()
  await expect(page.locator('.chart-warning')).toHaveText('1 series lost its data')
  await expect(page.locator('.chart-view')).toHaveAttribute('data-series-count', '1')
})
