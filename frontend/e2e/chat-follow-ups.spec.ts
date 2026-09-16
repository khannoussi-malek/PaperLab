import type { Page } from '@playwright/test'
import { ask, expect, pickChatModel, test } from './fixtures'

// Every answer here comes from this test's own connection, whatever the owner's default is.
test.beforeEach(async ({ page, llmConnection }) => {
  await pickChatModel(page, llmConnection.modelId)
})

/** Opens the reader on the Chat tab. */
async function openChat(page: Page, paperId: string) {
  await page.goto(`/#/papers/${paperId}?tab=chat`)
  await expect(page.getByRole('tab', { name: 'Chat' })).toHaveAttribute('aria-selected', 'true')
}

type Saved = { id: string; question: string; parent_id: string | null }

test('Follow up keeps a thread going under its first question until you stop following', async ({
  page,
  request,
  paperId,
}) => {
  await openChat(page, paperId)
  const first = await ask(page, 'What is the method?')
  const chip = page.locator('.chat-following')
  await expect(chip).toHaveCount(0)

  await first.getByRole('button', { name: 'Follow up' }).click()
  await expect(chip).toHaveText('Following: What is the method?')
  await expect(page.getByRole('textbox', { name: 'Question' })).toBeFocused()

  const second = await ask(page, 'And why that method?')
  const firstId = await first.getAttribute('data-output-id')
  await expect(second).toHaveAttribute('data-parent-id', firstId!)
  // One level in, under the first question.
  const [firstBox, secondBox] = [await first.boundingBox(), await second.boundingBox()]
  expect(secondBox!.x).toBeGreaterThan(firstBox!.x)
  // The chip moves to the newest answer: the next question continues the same thread.
  await expect(chip).toHaveText('Following: And why that method?')
  const third = await ask(page, 'Anything else?')
  await expect(third).toHaveAttribute('data-parent-id', (await second.getAttribute('data-output-id'))!)

  await page.getByRole('button', { name: 'Stop following' }).click()
  await expect(chip).toHaveCount(0)
  const fourth = await ask(page, 'A new question?')
  await expect(fourth).not.toHaveAttribute('data-parent-id')

  const saved: Saved[] = await (await request.get(`/api/papers/${paperId}/chat`)).json()
  const parentOf = (question: string) => saved.find((answer) => answer.question === question)!.parent_id
  expect(parentOf('And why that method?')).toBe(firstId)
  expect(parentOf('A new question?')).toBeNull()

  // A reload rebuilds the same threads from the saved answers.
  await page.reload()
  await expect(page.locator('article.chat-answer .chat-question')).toHaveText([
    'What is the method?',
    'And why that method?',
    'Anything else?',
    'A new question?',
  ])
  await expect(page.locator('article.chat-answer[data-parent-id]')).toHaveCount(2)
})

test('a follow-up on an older question joins that thread, above newer questions', async ({ page, paperId }) => {
  await openChat(page, paperId)
  const older = await ask(page, 'Older question?')
  await ask(page, 'Newer question?')

  await older.getByRole('button', { name: 'Follow up' }).click()
  await ask(page, 'Back to the older one?')

  await expect(page.locator('article.chat-answer .chat-question')).toHaveText([
    'Older question?',
    'Back to the older one?',
    'Newer question?',
  ])
})

test('a follow-up whose answer is gone says so and stops following', async ({ page, paperId }) => {
  await openChat(page, paperId)
  const first = await ask(page, 'Soon to be gone?')
  await page.route('**/chat', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'parent_not_found' }) })
      : route.fallback(),
  )

  await first.getByRole('button', { name: 'Follow up' }).click()
  await page.getByRole('textbox', { name: 'Question' }).fill('And then?')
  await page.getByRole('textbox', { name: 'Question' }).press('Enter')

  await expect(page.getByRole('alert')).toContainText('The answer you were following is gone.')
  await expect(page.getByRole('alert').getByRole('button', { name: 'Retry' })).toHaveCount(0)
  await expect(page.locator('.chat-following')).toHaveCount(0)
})

test('workspace chat offers no Follow up', async ({ page, workspaceId }) => {
  // A saved workspace answer, faked: a real one would need a retrieving question and the embedding model.
  const saved = {
    id: '00000000-0000-4000-8000-000000000701', question: 'Across papers?', content: 'Yes.', model: 'fake',
    connection_name: null, prompt_version: 1, created_at: new Date().toISOString(), whole_paper: false, sources: [],
    notes: [], notes_used: 0, notes_total: 0, parent_id: null,
  }
  await page.route(`**/api/workspaces/${workspaceId}/chat`, (route) =>
    route.request().method() === 'GET' ? route.fulfill({ json: [saved] }) : route.fallback(),
  )
  await page.goto(`/#/workspaces/${workspaceId}?tab=chat`)

  const answer = page.locator('article.chat-answer', { hasText: 'Across papers?' })
  await expect(answer.locator('.chat-answer-footer')).toBeVisible()
  await expect(answer.getByRole('button', { name: 'Follow up' })).toHaveCount(0)
})
