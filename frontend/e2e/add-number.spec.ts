import { expect, openReader, selectSubstring, TABLE_LINE, test } from './fixtures'

test('a selected number is saved with its error and unit, listed in the Data tab and underlined on the page', async ({
  page,
  request,
  tablePaperId,
}) => {
  const line = await openReader(page, tablePaperId, TABLE_LINE)
  await selectSubstring(line, '88.5 ± 0.3 F1')
  await page.getByRole('button', { name: 'Add as number' }).click()

  const dialog = page.getByRole('dialog', { name: 'Add as number' })
  const chosenChip = dialog.getByRole('radio', { name: '88.5 ± 0.3' })
  await expect(chosenChip).toHaveAttribute('aria-checked', 'true')
  await expect(chosenChip.locator('svg.lucide-check')).toBeVisible()
  await expect(dialog.getByRole('textbox', { name: 'Value' })).toHaveValue('88.5')
  await expect(dialog.getByRole('textbox', { name: '± error' })).toHaveValue('0.3')
  await expect(dialog.getByRole('textbox', { name: 'Unit' })).toHaveValue('F1')
  await expect(dialog.getByRole('button', { name: 'Add number' })).toBeDisabled()
  await dialog.getByRole('textbox', { name: 'Label' }).fill('Best dev F1')
  await dialog.getByRole('button', { name: 'Add number' }).click()
  await expect(dialog).toBeHidden()

  await page.getByRole('tab', { name: 'Data' }).click()
  await expect(page.locator('article.dataset-card')).toContainText('1 number')
  await expect(page.locator('.pdf-page[data-page="1"] .number-mark')).toHaveCount(1)

  const [numbers] = await (await request.get(`/api/datasets?paper_id=${tablePaperId}`)).json()
  const dataset = await (await request.get(`/api/datasets/${numbers.id}`)).json()
  const value = dataset.rows[0].cells.find((c: { value: number | null }) => c.value !== null)
  expect(value).toMatchObject({ raw: '88.5 ± 0.3', value: 88.5, error: 0.3, page: 1 })
})

test("the selection's right-click menu also adds it as a number", async ({ page, tablePaperId }) => {
  const line = await openReader(page, tablePaperId, TABLE_LINE)
  await selectSubstring(line, '88.5 ± 0.3 F1')
  const box = await line.boundingBox()
  await page.mouse.click(box!.x + box!.width * 0.4, box!.y + box!.height / 2, { button: 'right' })
  await page.getByRole('menuitem', { name: 'Add as number…' }).click()
  await expect(page.getByRole('dialog', { name: 'Add as number' })).toBeVisible()
})
