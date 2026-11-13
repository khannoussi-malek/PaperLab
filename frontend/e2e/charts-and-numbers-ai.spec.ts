import { addTable, expect, openReader, TABLE_LINE, test } from './fixtures'

test('Chart in chat draws a captured table, and Save chart keeps it', async ({ page, request, tablePaperId, dataName }) => {
  await addTable(request, tablePaperId, 1, `${dataName} table`, [
    ['System', 'F1'],
    ['BERT-B', '88.5'],
    ['BERT-L', '90.9'],
  ])
  await openReader(page, tablePaperId, TABLE_LINE)
  await page.getByRole('tab', { name: 'Chat' }).click()
  const question = page.getByRole('textbox', { name: 'Question' })
  await expect(question).toBeEnabled()
  await page.getByRole('button', { name: 'Chart' }).click()
  await question.fill(`${dataName} plot F1 by system`)
  await question.press('Enter')

  const answer = page.locator('article.chat-answer[data-output-id]', { hasText: `${dataName} plot F1 by system` })
  await expect(answer.locator('.chart-view .barlayer .point path').first()).toBeVisible({ timeout: 15_000 })
  await answer.getByRole('button', { name: 'Save chart' }).click()
  await expect(answer.getByRole('link', { name: 'Open saved chart' })).toBeVisible()
})

test('Suggest numbers lists a section’s numbers with quotes, and Add marks the label as the AI’s', async ({
  page,
  tablePaperId,
}) => {
  await openReader(page, tablePaperId, TABLE_LINE)
  await page.getByRole('tab', { name: 'Lens' }).click()
  const panel = page.getByRole('complementary', { name: 'Lens' })
  await panel.getByRole('button', { name: /Section actions for 1 Results/ }).click()
  await page.getByRole('menuitem', { name: 'Suggest numbers…' }).click()

  const dialog = page.getByRole('dialog', { name: /Numbers in 1 Results/ })
  const firstAdd = dialog.getByRole('button', { name: /^Add / }).first()
  await expect(firstAdd).toBeVisible({ timeout: 15_000 })
  await expect(dialog.getByText(/^p\. 1 · “/).first()).toBeVisible()
  await firstAdd.click()
  await expect(dialog.getByText('Added').first()).toBeVisible()
})
