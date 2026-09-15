import { addChart, addTable, barSpec, expect, openReader, test } from './fixtures'

test('fixing a cell marks it edited, and charts show the fixed value', async ({ page, request, paperId, dataName }) => {
  const table = await addTable(request, paperId, 1, `${dataName} table`, [
    ['System', 'F1'],
    ['BERT-B', '88.5'],
    ['BERT-L', '90.9'],
  ])
  const chart = await addChart(request, `${dataName} chart`, barSpec(table, 'System', ['F1']))

  await openReader(page, paperId)
  await page.getByRole('tab', { name: 'Data' }).click()
  await page.locator(`article.dataset-card[data-dataset-id="${table.id}"]`).getByRole('link', { name: 'Open' }).click()
  await expect(page.getByRole('heading', { name: `${dataName} table` })).toBeVisible()

  const cell = page.getByRole('textbox', { name: 'Row 2, column 2' })
  await expect(cell).toHaveValue('90.9')
  await cell.fill('91.0')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByRole('button', { name: 'Save' })).toBeDisabled()
  await page.reload()
  await expect(cell).toHaveValue('91.0')
  await expect(cell).toHaveAttribute('data-edited', 'true')
  await expect(page.getByRole('textbox', { name: 'Row 1, column 2' })).not.toHaveAttribute('data-edited', 'true')

  await page.goto(`/#/charts/${chart.id}`)
  await page.getByRole('button', { name: 'View data table' }).click()
  await expect(page.getByRole('table', { name: 'Chart data' })).toContainText('91.0 (edited)')
})

test('a header row joins the column names, fill down copies grouped labels, and removing a charted column asks first', async ({
  page,
  request,
  paperId,
  dataName,
}) => {
  const table = await addTable(request, paperId, 1, `${dataName} table`, [
    ['Group', 'Model', 'train'],
    ['', '', 'steps'],
    ['(A)', 'base', '100K'],
    ['', 'big', '300K'],
  ])
  await addChart(request, `${dataName} chart`, barSpec(table, 'Model', ['train']))
  await page.goto(`/#/datasets/${table.id}`)

  await page.getByRole('button', { name: 'Row 1 actions' }).click()
  await page.getByRole('menuitem', { name: 'Use as header' }).click()
  await expect(page.getByRole('textbox', { name: 'Column 3 name' })).toHaveValue('train / steps')

  await page.getByRole('button', { name: 'Column 1 actions' }).click()
  await page.getByRole('menuitem', { name: 'Fill down' }).click()
  await expect(page.getByRole('textbox', { name: 'Row 2, column 1' })).toHaveValue('(A)')

  await page.getByRole('button', { name: 'Column 3 actions' }).click()
  await page.getByRole('menuitem', { name: 'Delete column' }).click()
  await page.getByRole('button', { name: 'Save' }).click()
  const dialog = page.getByRole('dialog', { name: 'Charts use this data' })
  await expect(dialog.getByRole('link', { name: `${dataName} chart` })).toBeVisible()
  await dialog.getByRole('button', { name: 'Save anyway' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('textbox', { name: 'Column 3 name' })).toHaveCount(0)
  const saved = await (await request.get(`/api/datasets/${table.id}`)).json()
  expect(saved.columns.map((c: { name: string }) => c.name)).toEqual(['Group', 'Model'])
})

test("a link to one cell of a dataset focuses that cell", async ({ page, request, paperId, dataName }) => {
  const table = await addTable(request, paperId, 1, `${dataName} table`, [
    ['System', 'F1'],
    ['BERT-B', '88.5'],
    ['BERT-L', '90.9'],
  ])
  const dataset = await (await request.get(`/api/datasets/${table.id}`)).json()
  const [rowId, columnId] = [dataset.rows[1].id, dataset.columns[1].id]
  await page.goto(`/#/datasets/${table.id}?row=${rowId}&column=${columnId}`)
  await expect(page.getByRole('textbox', { name: 'Row 2, column 2' })).toBeFocused()
})

test('a failed delete shows the server error and leaves the dataset open', async ({ page, request, paperId, dataName }) => {
  const table = await addTable(request, paperId, 1, `${dataName} table`, [
    ['System', 'F1'],
    ['BERT-B', '88.5'],
  ])

  // Only this test's own page's requests are intercepted, and only this dataset's own endpoint (not its /grid
  // route), so this stays parallel-safe alongside the other specs hitting their own datasets.
  await page.route(`**/api/datasets/${table.id}`, async (route) => {
    if (route.request().method() === 'DELETE') await route.fulfill({ status: 500, json: { detail: 'Deleting failed' } })
    else await route.continue()
  })
  page.on('dialog', (dialog) => dialog.accept())

  await page.goto(`/#/datasets/${table.id}`)
  await expect(page.getByRole('heading', { name: `${dataName} table` })).toBeVisible()

  await page.getByRole('button', { name: 'Delete dataset' }).click()
  await expect(page.getByRole('alert')).toContainText('Deleting failed')
  await expect(page.getByRole('heading', { name: `${dataName} table` })).toBeVisible()
})
