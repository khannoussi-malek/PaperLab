import { addLlmConnection, expect, FAKE_BAD_KEY, test } from './fixtures'

const KEY = 'sk-test-SECRET123'

test('a keyed connection added from the library shows only its hint, and no page text or API response has the key', async ({
  page,
  llmName,
}) => {
  const bodies: Promise<string>[] = []
  page.on('response', (response) => {
    if (response.url().includes('/api/')) bodies.push(response.text().catch(() => ''))
  })
  await page.goto('/')
  await page.getByRole('link', { name: 'Settings' }).click()
  await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible()

  await page.getByRole('button', { name: 'Add connection' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add connection' })
  await dialog.getByRole('combobox', { name: 'Preset' }).click()
  await page.getByRole('option', { name: 'OpenRouter' }).click()
  await expect(dialog.getByRole('textbox', { name: 'Base URL' })).toHaveValue('https://openrouter.ai/api/v1')
  await dialog.getByRole('textbox', { name: 'Name' }).fill(llmName)
  await dialog.getByLabel('API key').fill(KEY)
  await dialog.getByRole('button', { name: 'Save connection' }).click()
  await expect(dialog).toBeHidden()

  const card = page.locator('article.connection-card', { hasText: llmName })
  await expect(card.locator('.key-hint')).toHaveText('•••• T123')
  await expect(card.locator('.cloud-tag')).toHaveText('Cloud')
  await expect(card).toContainText('Passages and notes from your library are sent to openrouter.ai')
  await page.reload()
  await expect(card.locator('.key-hint')).toHaveText('•••• T123')
  await expect(page.locator('body')).not.toContainText(KEY)
  for (const body of await Promise.all(bodies)) expect(body).not.toContain(KEY)
})

test('Test connection says when the key is rejected, and counts the models when it works', async ({ page, request, llmName }) => {
  const rejected = await addLlmConnection(request, `${llmName} rejected`, 'e2e-model', { api_key: FAKE_BAD_KEY })
  await addLlmConnection(request, `${llmName} working`, 'e2e-model', { api_key: 'sk-e2e-working' })
  await page.goto('/#/settings')

  const bad = page.locator('article.connection-card', { hasText: rejected.label })
  await bad.getByRole('button', { name: 'Test' }).click()
  await expect(bad.getByRole('status')).toHaveText(`Key rejected by ${rejected.label}`)

  const good = page.locator('article.connection-card', { hasText: `${llmName} working` })
  await good.getByRole('button', { name: 'Test' }).click()
  await expect(good.getByRole('status')).toHaveText('Connected · 2 models')
})

test('editing a connection renames it and removes its key, and deleting it asks first', async ({ page, request, llmName }) => {
  const connection = await addLlmConnection(request, llmName, 'e2e-model', { api_key: KEY })
  await page.goto('/#/settings')
  const card = page.locator(`article.connection-card[data-connection-id="${connection.id}"]`)

  await card.getByRole('button', { name: 'Edit connection' }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit connection' })
  await expect(dialog.getByRole('combobox', { name: 'Kind' })).toBeDisabled()
  await expect(dialog).toContainText('•••• T123')
  await dialog.getByRole('textbox', { name: 'Name' }).fill(`${llmName} renamed`)
  await dialog.getByRole('button', { name: 'Remove key' }).click()
  await dialog.getByRole('button', { name: 'Save connection' }).click()
  await expect(card.getByRole('heading', { name: `${llmName} renamed` })).toBeVisible()
  await expect(card.locator('.key-hint')).toHaveText('No key')

  page.once('dialog', (confirm) => void confirm.accept())
  await card.getByRole('button', { name: 'Delete connection' }).click()
  await expect(card).toHaveCount(0)
  expect((await (await request.get('/api/llm/connections')).json()).some((c: { id: string }) => c.id === connection.id)).toBe(false)
})

test('editing a keyed connection to a different host warns that saving will drop the key', async ({ page, request, llmName }) => {
  const connection = await addLlmConnection(request, llmName, 'e2e-model', { api_key: KEY })
  await page.goto('/#/settings')
  const card = page.locator(`article.connection-card[data-connection-id="${connection.id}"]`)

  await card.getByRole('button', { name: 'Edit connection' }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit connection' })
  await expect(dialog).not.toContainText('Changing the address removes the saved key.')
  await dialog.getByRole('textbox', { name: 'Base URL' }).fill('http://fake-provider-2.test/v1')
  await expect(dialog).toContainText('Changing the address removes the saved key.')
  await dialog.getByRole('button', { name: 'Save connection' }).click()
  await expect(dialog).toBeHidden()
  await expect(card.locator('.key-hint')).toHaveText('No key')
})
