import type { APIRequestContext } from '@playwright/test'
import { ask, expect, pickChatModel, test } from './fixtures'

// M8.5 Ask each paper. FakeLLM (backend LLM_PROVIDER=fake) finds every paper from its first passage ("The paper
// addresses this.") and answers the each-paper prompt as it answers workspace chat, citing [C1][C2].
const QUESTION = 'How does each paper describe the method?'
const SUMMARY = "Read 2 papers: 2 found, 0 don't cover this"

test.beforeEach(async ({ page, llmConnection }) => {
  await pickChatModel(page, llmConnection.modelId)
})

async function addToWorkspace(request: APIRequestContext, workspaceId: string, ...paperIds: string[]) {
  for (const id of paperIds) expect((await request.put(`/api/workspaces/${workspaceId}/papers/${id}`)).status()).toBe(204)
}

test('Ask each paper reads every paper, answers from their records and keeps them after a reload', async ({
  page,
  request,
  paperId,
  secondPaperId,
  workspaceId,
}) => {
  test.slow() // a retrieving question, possibly the suite's first: it also loads the embedding model
  await addToWorkspace(request, workspaceId, paperId, secondPaperId)
  await page.goto(`/#/workspaces/${workspaceId}?tab=chat`)

  // A per-paper question gets the hint; taking it switches the mode on.
  await page.getByRole('textbox', { name: 'Question' }).fill(QUESTION)
  await page.getByRole('button', { name: 'Sounds like a question for each paper · Ask each paper' }).click()
  await expect(page.getByRole('button', { name: 'Ask each paper' })).toHaveAttribute('aria-pressed', 'true')

  const answer = await ask(page, QUESTION, 60_000)
  await expect(answer.locator('.chat-cite').first()).toHaveText('[C1]')
  const summary = answer.getByText(SUMMARY)
  await expect(summary).toBeVisible()
  await summary.click()
  await expect(answer.getByText('The paper addresses this.')).toHaveCount(2)

  const [saved] = await (await request.get(`/api/workspaces/${workspaceId}/chat`)).json()
  expect(saved.readings.map((r: { paper_id: string }) => r.paper_id).sort()).toEqual([paperId, secondPaperId].sort())
  expect(saved.sources).toHaveLength(2)

  await page.reload()
  await expect(page.locator('article.chat-answer[data-output-id]').getByText(SUMMARY)).toBeVisible()
})
