import { dragBox, expect, openReader, TABLE_LINE, test } from './fixtures'

test('drawing a box over a table previews its grid; fixing it and saving outlines the table and lists it', async ({ page, request, tablePaperId }) => {
  await openReader(page, tablePaperId, TABLE_LINE)
  const toggle = page.getByRole('button', { name: 'Capture table' })
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-pressed', 'true')
  await dragBox(page, 1, [60, 145, 420, 200])

  const dialog = page.getByRole('dialog', { name: 'Capture table' })
  await expect(dialog.getByRole('textbox', { name: 'Table name' })).toHaveValue('Table 1: Results on the dev set.')
  await expect(dialog.locator('canvas.capture-crop')).toBeVisible()
  await expect(dialog.getByRole('textbox', { name: 'Row 2, column 2' })).toHaveValue('88.5')

  await dialog.getByRole('button', { name: 'Row 1 actions' }).click()
  await page.getByRole('menuitem', { name: 'Use as header' }).click()
  await expect(dialog.getByRole('textbox', { name: 'Column 2 name' })).toHaveValue('Dev F1')
  await dialog.getByRole('textbox', { name: 'Row 1, column 2' }).fill('88.6')
  await dialog.getByRole('button', { name: 'Save table' }).click()
  await expect(dialog).toBeHidden()

  await expect(page.locator('.pdf-page[data-page="1"] .table-region')).toHaveCount(1)
  await expect(page.getByRole('tab', { name: 'Data' })).toHaveAttribute('aria-selected', 'true')
  const card = page.locator('article.dataset-card', { hasText: 'Table 1: Results on the dev set.' })
  await expect(card).toContainText('p. 1 · 2 rows × 3 columns')

  const [saved] = await (await request.get(`/api/datasets?paper_id=${tablePaperId}`)).json()
  const dataset = await (await request.get(`/api/datasets/${saved.id}`)).json()
  expect(dataset.rows[0].cells[1]).toMatchObject({ raw: '88.6', value: 88.6, original_raw: '88.5', page: 1 })

  await card.getByRole('link', { name: 'Open' }).click()
  await expect(page.getByRole('textbox', { name: 'Row 1, column 2' })).toHaveAttribute('data-edited', 'true')
})

test('capture mode stops text selection, a click-sized drag does nothing, and Escape leaves the mode', async ({ page, tablePaperId }) => {
  await openReader(page, tablePaperId, TABLE_LINE)
  await page.getByRole('button', { name: 'Capture table' }).click()
  await expect(page.locator('section.cursor-crosshair')).toHaveCount(1)
  await dragBox(page, 1, [100, 150, 104, 153])
  await expect(page.getByRole('dialog', { name: 'Capture table' })).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: 'Note' })).toHaveCount(0)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Capture table' })).toHaveAttribute('aria-pressed', 'false')
})
