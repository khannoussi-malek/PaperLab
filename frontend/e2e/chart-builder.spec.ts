import { addChart, addNote, addOwnData, addTable, barSpec, expect, openReader, test } from './fixtures'

test('a bar chart built from a paper table and your own data previews both series and saves', async ({ page, request, paperId, dataName }) => {
  const table = await addTable(request, paperId, 1, `${dataName} table`, [
    ['System', 'F1'],
    ['BERT-B', '88.5'],
    ['BERT-L', '90.9'],
  ])
  const runs = await addOwnData(request, `${dataName} runs`, 'run,F1\nmine,92.0\n')

  await page.goto('/#/charts/new')
  await expect(page.getByRole('radio', { name: 'Bar', exact: true })).toHaveAttribute('aria-checked', 'true')
  await expect(page.getByText('Add a series to start the chart.')).toBeVisible()
  for (const id of [table.id, runs.id]) {
    await page.getByRole('button', { name: 'Add series' }).click()
    await page.getByRole('dialog', { name: 'Choose data' }).locator(`[data-dataset-id="${id}"]`).click()
  }
  await expect(page.locator('.series-card')).toHaveCount(2)
  await expect(page.locator('.chart-view')).toHaveAttribute('data-series-count', '2')

  await page.getByRole('textbox', { name: 'Chart title' }).fill(`${dataName} comparison`)
  await page.getByRole('button', { name: 'Save chart' }).click()
  await expect(page).toHaveURL(/#\/charts\/[0-9a-f-]{36}$/)
  await expect(page.getByRole('heading', { name: `${dataName} comparison` })).toBeVisible()
  await expect(page.locator('.chart-view')).toHaveAttribute('data-series-count', '2')
})

test('two quick picks both add a series, even when the first dataset loads after the second pick', async ({ page, request, dataName }) => {
  const first = await addOwnData(request, `${dataName} first`, 'run,F1\nmine,92.0\n')
  const second = await addOwnData(request, `${dataName} second`, 'run,Acc\nmine,71.5\n')
  for (const id of [first.id, second.id]) {
    await page.route(`**/api/datasets/${id}`, async (route) => {
      await new Promise((ok) => setTimeout(ok, 800))
      await route.continue()
    })
  }

  await page.goto('/#/charts/new')
  for (const id of [first.id, second.id]) {
    await page.getByRole('button', { name: 'Add series' }).click()
    await page.getByRole('dialog', { name: 'Choose data' }).locator(`[data-dataset-id="${id}"]`).click()
  }
  await expect(page.locator('.series-card')).toHaveCount(2)
  await expect(page.locator('.chart-view')).toHaveAttribute('data-series-count', '2')
})

test("Quick chart from the Data tab charts every number column, and too many series in one panel can't be saved", async ({
  page,
  request,
  paperId,
  dataName,
}) => {
  await addTable(request, paperId, 1, `${dataName} table`, [
    ['System', 'Dev F1', 'Test F1'],
    ['BERT-B', '88.5', '87.0'],
    ['BERT-L', '90.9', '91.8'],
  ])
  await openReader(page, paperId)
  await page.getByRole('tab', { name: 'Data' }).click()
  await page.locator('article.dataset-card').getByRole('link', { name: 'Quick chart' }).click()
  await expect(page).toHaveURL(/#\/charts\/new\?dataset=/)
  await expect(page.locator('.series-card')).toHaveCount(2)
  await expect(page.getByRole('textbox', { name: 'Chart title' })).toHaveValue(`${dataName} table`)

  await page.getByRole('radio', { name: 'Scatter', exact: true }).click()
  await expect(page.locator('.chart-view')).toHaveAttribute('data-chart-type', 'scatter')
  await page.getByRole('button', { name: 'Add series' }).click()
  await page.getByRole('dialog', { name: 'Choose data' }).locator('[data-dataset-id]', { hasText: `${dataName} table` }).click()
  await page.getByRole('button', { name: 'Add series' }).click()
  await page.getByRole('dialog', { name: 'Choose data' }).locator('[data-dataset-id]', { hasText: `${dataName} table` }).click()
  await expect(page.getByText('Scatter charts show at most 3 series in one panel. Turn on small multiples, or remove a series.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save chart' })).toBeDisabled()
  await page.getByRole('checkbox', { name: 'Small multiples' }).check()
  await expect(page.getByRole('button', { name: 'Save chart' })).toBeEnabled()
})

test('editing a chart that a note shows warns, and Save as copy leaves the original unchanged', async ({ page, request, paperId, dataName }) => {
  const table = await addTable(request, paperId, 1, `${dataName} table`, [
    ['System', 'F1'],
    ['BERT-B', '88.5'],
  ])
  const chart = await addChart(request, `${dataName} chart`, barSpec(table, 'System', ['F1']))
  const note = await addNote(request, paperId, 1, 'Shows the chart')
  expect((await request.put(`/api/notes/${note.id}/charts/${chart.id}`)).status()).toBe(204)

  await page.goto(`/#/charts/${chart.id}`)
  await page.getByRole('link', { name: 'Edit' }).click()
  await expect(page.getByText('Used in 1 note, which will show this change')).toBeVisible()
  await page.getByRole('radio', { name: 'Line', exact: true }).click()
  await page.getByRole('button', { name: 'Save as copy' }).click()

  await expect(page.getByRole('heading', { name: `${dataName} chart (copy)` })).toBeVisible()
  expect(page.url()).not.toContain(chart.id)
  await expect(page.locator('.chart-view')).toHaveAttribute('data-chart-type', 'line')
  const original = await (await request.get(`/api/charts/${chart.id}`)).json()
  expect(original.spec.type).toBe('bar')
  expect(original.note_ids).toEqual([note.id])
})

test('adding a series keeps the last drawing without data warnings while the new data resolves', async ({ page, request, dataName }) => {
  const first = await addOwnData(request, `${dataName} first`, 'run,F1\nmine,92.0\n')
  const second = await addOwnData(request, `${dataName} second`, 'run,Acc\nmine,71.5\n')

  await page.goto('/#/charts/new')
  await page.getByRole('button', { name: 'Add series' }).click()
  await page.getByRole('dialog', { name: 'Choose data' }).locator(`[data-dataset-id="${first.id}"]`).click()
  await expect(page.locator('.chart-view')).toHaveAttribute('data-series-count', '1')

  // Any warning drawn from here on is recorded, however briefly it shows.
  await page.evaluate(() => {
    const seen = window as unknown as { warned: boolean }
    seen.warned = false
    new MutationObserver(() => {
      if (document.querySelector('.chart-warning')) seen.warned = true
    }).observe(document.body, { childList: true, subtree: true, characterData: true })
  })
  await page.route('**/api/charts/resolve', async (route) => {
    await new Promise((ok) => setTimeout(ok, 1500))
    await route.continue()
  })
  await page.getByRole('button', { name: 'Add series' }).click()
  await page.getByRole('dialog', { name: 'Choose data' }).locator(`[data-dataset-id="${second.id}"]`).click()
  await expect(page.locator('.chart-view .opacity-60')).toBeVisible()
  await expect(page.locator('.chart-view')).toHaveAttribute('data-series-count', '2')
  expect(await page.evaluate(() => (window as unknown as { warned: boolean }).warned)).toBe(false)
})
