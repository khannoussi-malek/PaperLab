import { ask, expect, test } from './fixtures'

test('checking an answer marks each cited sentence, and the marks are still there after a reload', async ({
  page,
  paperId,
}) => {
  await page.goto(`/#/papers/${paperId}?tab=chat`)
  await expect(page.getByRole('tab', { name: 'Chat' })).toHaveAttribute('aria-selected', 'true')
  const answer = await ask(page, 'What is the method?')

  await answer.getByRole('button', { name: 'Check this answer' }).click()
  const check = answer.getByRole('region', { name: 'Answer check' })
  // The fake model supports every cited sentence with a quote from its first passage.
  await expect(check.getByText(/Checked by .* supported/)).toBeVisible({ timeout: 30_000 })
  await expect(check.getByText('Supported').first()).toBeVisible()
  await expect(check.getByText('AI check').first()).toBeVisible()

  await page.reload()
  const again = page.locator('article.chat-answer[data-output-id]', { hasText: 'What is the method?' })
  await expect(again.getByText(/Checked by .* supported/)).toBeVisible()
  await expect(again.getByRole('button', { name: 'Check again' })).toBeVisible()
})
