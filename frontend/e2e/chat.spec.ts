import { expect, openReader, selectText, test } from './fixtures'

test('the Chat tab is kept in the hash across a reload, and selecting text returns to Notes', async ({
  page,
  paperId,
}) => {
  const line = await openReader(page, paperId)
  const notesTab = page.getByRole('tab', { name: 'Notes' })
  const chatTab = page.getByRole('tab', { name: 'Chat' })
  await expect(notesTab).toHaveAttribute('aria-selected', 'true')

  await chatTab.click()
  await expect(page).toHaveURL(new RegExp(`#/papers/${paperId}\\?tab=chat$`))
  await page.reload()
  await expect(chatTab).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('complementary', { name: 'Notes' })).toBeHidden()

  // The note composer lives on the Notes tab, so a new selection brings it back.
  await expect(line).toBeVisible()
  await selectText(line)
  await expect(notesTab).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('textbox', { name: 'Note' })).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`#/papers/${paperId}$`))
})
