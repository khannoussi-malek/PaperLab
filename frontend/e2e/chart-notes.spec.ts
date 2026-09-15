import { addChart, addNote, addOwnData, addTable, barSpec, expect, openReader, test } from './fixtures'

test("Add to note puts the chart in its source paper's notes, drawn inside the note", async ({ page, request, paperId, dataName }) => {
  const table = await addTable(request, paperId, 1, `${dataName} table`, [
    ['System', 'F1'],
    ['BERT-B', '88.5'],
  ])
  const chart = await addChart(request, `${dataName} chart`, barSpec(table, 'System', ['F1']))
  await page.goto(`/#/charts/${chart.id}`)
  await page.getByRole('button', { name: 'Chart actions' }).click()
  await page.getByRole('menuitem', { name: 'Add to note…' }).click()

  const added = page.getByRole('status').filter({ hasText: 'Added to a note in 1 paper.' })
  await expect(added).toBeVisible()
  await added.getByRole('link', { name: 'Open the note' }).click()
  const embed = page.locator(`article.note .note-chart[data-chart-id="${chart.id}"]`)
  await expect(embed.getByRole('link', { name: `${dataName} chart` })).toBeVisible()
  await expect(embed.locator('.chart-view')).toHaveAttribute('data-series-count', '1')
})

test('a chart attached to an existing note can be removed again, keeping the note', async ({ page, request, paperId, dataName }) => {
  const table = await addTable(request, paperId, 1, `${dataName} table`, [
    ['System', 'F1'],
    ['BERT-B', '88.5'],
  ])
  const chart = await addChart(request, `${dataName} chart`, barSpec(table, 'System', ['F1']))
  await addNote(request, paperId, 1, 'A note for a chart')
  await openReader(page, paperId)
  const card = page.locator('article.note', { hasText: 'A note for a chart' })
  await card.getByRole('button', { name: 'Attach chart' }).click()
  await page.getByRole('dialog', { name: 'Attach chart' }).locator(`[data-chart-id="${chart.id}"]`).click()

  const embed = card.locator(`.note-chart[data-chart-id="${chart.id}"]`)
  await expect(embed).toBeVisible()
  await embed.getByRole('button', { name: 'Remove chart' }).click()
  await expect(embed).toHaveCount(0)
  await expect(card).toBeVisible()
})

test('a chart of only your own data explains why it cannot become a note', async ({ page, request, dataName }) => {
  const runs = await addOwnData(request, `${dataName} runs`, 'run,F1\nmine,92.0\n')
  const chart = await addChart(request, `${dataName} chart`, barSpec(runs, 'run', ['F1']))
  await page.goto(`/#/charts/${chart.id}`)
  await page.getByRole('button', { name: 'Chart actions' }).click()
  await page.getByRole('menuitem', { name: 'Add to note…' }).click()
  await expect(page.getByRole('alert')).toContainText("This chart only uses your own data, so there's no paper to note it in.")
})
