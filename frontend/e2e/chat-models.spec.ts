import type { APIRequestContext, Page } from '@playwright/test'
import { addLlmConnection, ask, expect, openReader, test } from './fixtures'

async function addSecondModel(request: APIRequestContext, connectionId: string, name: string) {
  const added = await request.post(`/api/llm/connections/${connectionId}/models`, { data: { name } })
  expect(added.status()).toBe(201)
  return (await added.json()) as { id: string; name: string }
}

async function chooseModel(page: Page, optionName: string) {
  await page.getByRole('combobox', { name: 'Model' }).click()
  await page.getByRole('option', { name: optionName }).click()
}

test('switching the model in paper chat answers with it, marks a cloud model, and keeps the pick after a reload', async ({
  page,
  request,
  paperId,
  llmConnection,
}) => {
  await addSecondModel(request, llmConnection.id, 'e2e-second')
  await page.goto(`/#/papers/${paperId}?tab=chat`)

  await page.getByRole('combobox', { name: 'Model' }).click()
  const option = page.getByRole('option', { name: `e2e-second · ${llmConnection.label}` })
  await expect(option.locator('.cloud-tag')).toHaveText('Cloud')
  await option.click()
  // The closed trigger shows a clean truncated label, not the whole selected item: no Cloud badge leaks into it.
  await expect(page.getByRole('combobox', { name: 'Model' }).locator('.cloud-tag')).toHaveCount(0)
  const answer = await ask(page, 'Second model?')
  await expect(answer.locator('.chat-answer-footer')).toHaveText(`AI · fake:e2e-second · ${llmConnection.label} · prompt v6`)

  await page.reload()
  await expect(page.getByRole('combobox', { name: 'Model' })).toContainText(`e2e-second · ${llmConnection.label}`)
})

test('the same switch works in workspace chat', async ({ page, request, paperId, workspaceId, llmConnection }) => {
  test.slow() // workspace chat retrieves: the first question can pay for loading the embedding model
  await addSecondModel(request, llmConnection.id, 'e2e-second')
  expect((await request.put(`/api/workspaces/${workspaceId}/papers/${paperId}`)).status()).toBe(204)
  await page.goto(`/#/workspaces/${workspaceId}?tab=chat`)

  await chooseModel(page, `e2e-second · ${llmConnection.label}`)
  const answer = await ask(page, 'Second model here too?', 45_000)

  await expect(answer.locator('.chat-answer-footer')).toHaveText(`AI · fake:e2e-second · ${llmConnection.label} · prompt v5`)
})

test('a model removed while it is picked says so, and the dropdown falls back to the default', async ({
  page,
  request,
  paperId,
  llmName,
}) => {
  const doomed = await addLlmConnection(request, `${llmName} doomed`, 'e2e-doomed')
  await page.goto(`/#/papers/${paperId}?tab=chat`)
  await chooseModel(page, `e2e-doomed · ${doomed.label}`)
  expect((await request.delete(`/api/llm/connections/${doomed.id}`)).status()).toBe(204)

  const question = page.getByRole('textbox', { name: 'Question' })
  await question.fill('Still there?')
  await question.press('Enter')

  await expect(page.locator('article.chat-answer', { hasText: 'Still there?' }).getByRole('alert')).toContainText(
    'The model you picked was removed',
  )
  await expect(page.getByRole('combobox', { name: 'Model' })).not.toContainText(doomed.label)
})

test('with no models at all, the chat panel links to settings instead of a dropdown', async ({ page, paperId }) => {
  // The owner's database always has models, so this state is faked.
  await page.route('**/api/llm/models', (route) => route.fulfill({ json: [] }))
  await page.goto(`/#/papers/${paperId}?tab=chat`)

  await expect(page.getByRole('combobox', { name: 'Model' })).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: 'Question' })).toBeDisabled()
  await page.getByRole('link', { name: 'Set up a model' }).click()
  await expect(page).toHaveURL(/#\/settings$/)
})

// `@moves-default`: this one marks a model default, moving the row every other spec snapshots. The tag puts it
// in the single-worker project that runs last (playwright.config.ts), so nothing else is mid-test while it moves.
test('a model added by name and made the default answers the next question, and its footer survives a reload', {
  tag: '@moves-default',
}, async ({ page, llmConnection, paperId }) => {
  const name = `e2e-default-${llmConnection.label.slice(-8)}`
  await page.goto('/#/settings')
  const card = page.locator(`article.connection-card[data-connection-id="${llmConnection.id}"]`)
  await card.getByRole('button', { name: 'Add model' }).click()
  await page.getByRole('combobox', { name: 'Search or type a model name' }).fill(name)
  await page.getByRole('option', { name: `Add “${name}”` }).click()
  await card.getByRole('radiogroup', { name: 'Default model' }).getByRole('radio', { name }).click()
  await expect(card.getByRole('radio', { name })).toBeChecked()

  await openReader(page, paperId)
  await page.getByRole('tab', { name: 'Chat' }).click()
  const answer = await ask(page, 'Which model answers?')
  const footer = `AI · fake:${name} · ${llmConnection.label} · prompt v6`
  await expect(answer.locator('.chat-answer-footer')).toHaveText(footer)

  await page.reload()
  await expect(page.locator('article.chat-answer', { hasText: 'Which model answers?' }).locator('.chat-answer-footer')).toHaveText(footer)
})
