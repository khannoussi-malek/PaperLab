import { ask, expect, test } from './fixtures'

test('an answer shows how it was made, and its citation survives a re-ingest of the paper', async ({
  page,
  request,
  paperId,
}) => {
  await page.goto(`/#/papers/${paperId}?tab=chat`)
  await expect(page.getByRole('tab', { name: 'Chat' })).toHaveAttribute('aria-selected', 'true')
  const answer = await ask(page, 'What is the method?')

  await answer.getByRole('button', { name: 'How this was made' }).click()
  await expect(answer.getByText('Model', { exact: true })).toBeVisible()
  await expect(answer.getByText('Still in the paper').first()).toBeVisible()

  // A re-ingest replaces every chunk: the cited passage was snapshotted, so it still reads and still opens.
  expect((await request.post(`/api/papers/${paperId}/reingest`)).status()).toBe(202)
  await expect
    .poll(async () => (await (await request.get(`/api/papers/${paperId}`)).json()).status, { timeout: 30_000 })
    .toBe('ready')

  await page.reload()
  const again = page.locator('article.chat-answer[data-output-id]', { hasText: 'What is the method?' })
  await again.getByRole('button', { name: 'How this was made' }).click()
  await expect(again.getByText('Still in the paper').first()).toBeVisible()
  await expect(again.locator('.chat-cite')).toHaveText(['[C1]'])
  await again.locator('.chat-cite').first().click()
  await expect(page).toHaveURL(new RegExp(`papers/${paperId}`))
})
