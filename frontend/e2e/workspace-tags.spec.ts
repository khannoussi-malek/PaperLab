import { expect, test } from './fixtures'

test('tag papers, filter by a tag, rename it, and delete another without deleting papers', async ({
  page,
  request,
  paperId,
  secondPaperId,
  workspaceId,
}) => {
  for (const id of [paperId, secondPaperId]) {
    expect((await request.put(`/api/workspaces/${workspaceId}/papers/${id}`)).ok()).toBe(true)
  }
  await page.goto(`/#/workspaces/${workspaceId}`)
  // The fixture papers share a title, so rows are told apart by their reader link.
  const row = (id: string) => page.locator('.paper-row').filter({ has: page.locator(`a[href="#/papers/${id}"]`) })
  await expect(row(paperId)).toBeVisible()
  await expect(row(secondPaperId)).toBeVisible()

  // Tag both papers Q1.
  await row(paperId).getByRole('checkbox').check()
  await row(secondPaperId).getByRole('checkbox').check()
  await expect(page.getByText('2 selected')).toBeVisible()
  await page.getByRole('button', { name: 'Tag…', exact: true }).click()
  await page.getByPlaceholder('Find or create a tag').fill('Q1')
  await page.getByRole('option', { name: 'Create "Q1"' }).click()
  await expect(row(paperId).getByRole('button', { name: 'Filter by tag Q1' })).toBeVisible()
  await expect(row(secondPaperId).getByRole('button', { name: 'Filter by tag Q1' })).toBeVisible()

  // Tag only the first paper Q2.
  await row(paperId).getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Tag…', exact: true }).click()
  await page.getByPlaceholder('Find or create a tag').fill('Q2')
  await page.getByRole('option', { name: 'Create "Q2"' }).click()
  await expect(row(paperId).getByRole('button', { name: 'Filter by tag Q2' })).toBeVisible()

  // Filtering by the Q2 chip leaves only the first paper.
  await row(paperId).getByRole('button', { name: 'Filter by tag Q2' }).click()
  await expect(page).toHaveURL(/tags=Q2/)
  await expect(row(paperId)).toBeVisible()
  await expect(row(secondPaperId)).toHaveCount(0)

  // Renaming Q2 keeps the filter, under the new name; Escape returns focus to the button.
  await page.getByRole('button', { name: 'Actions for tag Q2' }).click()
  await page.getByRole('menuitem', { name: 'Rename' }).click()
  await page.getByRole('textbox', { name: 'Tag name' }).fill('Q2b')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page).toHaveURL(/tags=Q2b/)
  await expect(page.getByRole('button', { name: /^Q2b, 1 paper$/ })).toHaveAttribute('aria-pressed', 'true')

  await page.getByRole('button', { name: 'Actions for tag Q2b' }).click()
  await page.getByRole('menuitem', { name: 'Rename' }).click()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Actions for tag Q2b' })).toBeFocused()

  // Deleting Q1 removes the tag, not the papers.
  await page.getByRole('button', { name: 'Actions for tag Q1' }).click()
  await page.getByRole('menuitem', { name: 'Delete' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('The tag is removed from 2 papers. No papers are deleted.')).toBeVisible()
  await dialog.getByRole('button', { name: 'Delete' }).click()
  await expect(page.getByRole('button', { name: /^Q1, / })).toHaveCount(0)
  await page.getByRole('button', { name: /^Q2b, 1 paper$/ }).click() // clear the filter
  await expect(row(paperId)).toBeVisible()
  await expect(row(secondPaperId)).toBeVisible()
})
