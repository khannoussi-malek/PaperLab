import { addLlmConnection, expect, test } from './fixtures'

test('pulling a model shows its progress live and ends with the model listed, and deleting it from disk asks first', async ({
  page,
  request,
  llmName,
}) => {
  const connection = await addLlmConnection(request, llmName, 'e2e-model', { kind: 'ollama', base_url: 'http://fake-ollama.test:11434' })
  await page.goto('/#/settings')
  const card = page.locator(`article.connection-card[data-connection-id="${connection.id}"]`)
  // Every value the progress bar shows, in order, as the page draws it: polling could miss a step.
  await page.evaluate(() => {
    const seen: string[] = []
    Object.assign(window, { pullValues: seen })
    new MutationObserver(() => {
      const value = document.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')
      if (value && seen.at(-1) !== value) seen.push(value)
    }).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['aria-valuenow'] })
  })

  await card.getByRole('textbox', { name: 'Model to pull' }).fill('e2e-pulled')
  await card.getByRole('button', { name: 'Pull' }).click()
  await expect(card.getByRole('progressbar', { name: 'Pulling e2e-pulled' })).toBeVisible()
  const row = card.locator('li.model-row', { hasText: 'e2e-pulled' })
  await expect(row).toBeVisible({ timeout: 15_000 })

  const values = await page.evaluate(() => (window as unknown as { pullValues: string[] }).pullValues.map(Number))
  expect(values.length).toBeGreaterThanOrEqual(3)
  expect(values).toEqual([...values].sort((a, b) => a - b))
  expect(values.at(-1)).toBe(100)

  page.once('dialog', (confirm) => void confirm.accept())
  await row.getByRole('button', { name: 'Delete e2e-pulled from disk' }).click()
  await expect(row).toHaveCount(0)
})
