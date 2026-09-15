import type { APIRequestContext } from '@playwright/test'
import { FIXTURE_TITLE, addNote, ask, expect, pickChatModel, selectAllOf, test } from './fixtures'

/** What `FakeLLM` answers to the workspace prompt (backend `LLM_PROVIDER=fake`). */
const FAKE_WORKSPACE_ANSWER =
  'Fake workspace answer: both papers describe the method [C1][C2], as your note says [N1].'
const QUESTION = 'Which method do these papers describe?'

type Source = { label: string; chunk_id: string; paper_id: string; page: number }

// Every answer here comes from this test's own connection, whatever the owner's default is.
test.beforeEach(async ({ page, llmConnection }) => {
  await pickChatModel(page, llmConnection.modelId)
})

async function addToWorkspace(request: APIRequestContext, workspaceId: string, ...paperIds: string[]) {
  for (const id of paperIds) expect((await request.put(`/api/workspaces/${workspaceId}/papers/${id}`)).status()).toBe(204)
}

// Both papers are copies of the fixture, so they hold the same chunks. Workspace chat always retrieves (no whole-paper
// shortcut) with at most 3 chunks per paper, ranked by distance. Equal text embeds to an equal vector, so
// the two nearest passages, C1 and C2, are the same chunk from each paper, in either order: the test reads which
// paper each came from out of the answer's saved sources, the same list the stream's `sources` event sent.
test('a workspace answer cites a passage from each paper and a note, and each citation opens the reader there', async ({
  page,
  request,
  paperId,
  secondPaperId,
  workspaceId,
}) => {
  // Workspace chat always retrieves (no whole-paper shortcut), so this is the suite's first retrieving
  // question on a freshly recreated API: it also pays for loading the embedding model (~3.4s cold, more under load).
  test.slow()
  await addToWorkspace(request, workspaceId, paperId, secondPaperId)
  const note = await addNote(request, secondPaperId, 1, 'My note on the introduction')
  await page.goto(`/#/workspaces/${workspaceId}?tab=chat`)
  await expect(page.locator('.chat-scope')).toHaveText('2 papers · 1 note')

  const answer = await ask(page, QUESTION, 45_000)
  await expect(answer.locator('.chat-answer-text')).toHaveText(FAKE_WORKSPACE_ANSWER)
  await expect(answer.locator('.chat-cite')).toHaveText(['[C1]', '[C2]', '[N1]'])
  // Pills stay short; their names say which paper, and that N1 is the user's note.
  const pills = answer.locator('.chat-sources')
  await expect(pills.getByRole('button', { name: new RegExp(`^Source 1: ${FIXTURE_TITLE}, page \\d`) })).toBeVisible()
  await expect(pills.getByRole('button', { name: `N1 · You · ${FIXTURE_TITLE} p.1` })).toBeVisible()

  const [saved] = await (await request.get(`/api/workspaces/${workspaceId}/chat`)).json()
  const [c1, c2] = saved.sources as Source[]
  expect(new Set([c1.paper_id, c2.paper_id])).toEqual(new Set([paperId, secondPaperId]))
  expect(saved.notes[0]).toMatchObject({ label: 'N1', note_id: note.id, paper_id: secondPaperId })

  // [C1] opens its paper and flashes the passage; Back returns to the answer.
  await answer.locator('.chat-cite', { hasText: '[C1]' }).click()
  await expect(page.locator(`.pdf-page[data-page="${c1.page}"] .chunk-flash`).first()).toBeInViewport()
  await expect(page).toHaveURL(new RegExp(`#/papers/${c1.paper_id}$`))
  await page.goBack()
  await expect(page.getByRole('tab', { name: 'Chat' })).toHaveAttribute('aria-selected', 'true')

  // [N1] opens the note's paper with the note focused.
  await page.locator('article.chat-answer[data-output-id] .chat-cite', { hasText: '[N1]' }).click()
  await expect(page.locator(`.highlight.active[data-note-id="${note.id}"]`)).toBeInViewport()
  await expect(page).toHaveURL(new RegExp(`#/papers/${secondPaperId}$`))
})

test('saving a workspace answer as a note anchors it on both cited passages and lists it in the Notes tab', async ({
  page,
  request,
  paperId,
  secondPaperId,
  workspaceId,
}) => {
  await addToWorkspace(request, workspaceId, paperId, secondPaperId)
  await addNote(request, secondPaperId, 1, 'My note on the introduction')
  await page.goto(`/#/workspaces/${workspaceId}?tab=chat`)
  const answer = await ask(page, QUESTION)

  // A selection citing only [N1] has no passage to anchor on, even though its sentence cites [C1][C2].
  await selectAllOf(answer.locator('.chat-cite', { hasText: '[N1]' }))
  await expect(page.getByRole('button', { name: 'Save as note' })).toBeDisabled()

  await selectAllOf(answer.locator('.chat-answer-text'))
  await page.getByRole('button', { name: 'Save as note' }).click()
  await expect(page.getByRole('tab', { name: 'Notes' })).toHaveAttribute('aria-selected', 'true')
  const card = page.locator('a.workspace-note', { hasText: FAKE_WORKSPACE_ANSWER })
  await expect(card.locator('.provenance-badge')).toHaveText('AI')

  const [saved] = await (await request.get(`/api/workspaces/${workspaceId}/chat`)).json()
  const notes = await (await request.get(`/api/workspaces/${workspaceId}/notes`)).json()
  const promoted = notes.find((n: { provenance: string }) => n.provenance === 'llm')
  expect(promoted.source_id).toBe(saved.id)
  expect(new Set(promoted.anchors.map((a: { paper_id: string }) => a.paper_id))).toEqual(new Set([paperId, secondPaperId]))
})

test('an empty workspace asks for papers, and a refused or trimmed answer says why', async ({
  page,
  request,
  paperId,
  workspaceId,
}) => {
  await page.goto(`/#/workspaces/${workspaceId}?tab=chat`)
  await expect(page.getByRole('heading', { name: 'Ask this workspace' })).toBeVisible()
  await expect(page.getByText('Add papers to chat with this workspace.')).toBeVisible()
  const question = page.getByRole('textbox', { name: 'Question' })
  await expect(question).toBeDisabled()
  await expect(page.getByRole('list', { name: 'Suggested questions' }).getByRole('button').first()).toBeDisabled()

  await addToWorkspace(request, workspaceId, paperId)
  await page.reload()
  await expect(question).toBeEnabled()

  // The real stack indexes every fixture paper and has too few notes to trim, so these two responses are faked.
  await page.route('**/chat', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 409, contentType: 'application/json', body: '{"detail":"workspace_not_indexed"}' })
      : route.fallback(),
  )
  await question.fill('Not indexed?')
  await question.press('Enter')
  const refused = page.locator('article.chat-answer', { hasText: 'Not indexed?' })
  await expect(refused.getByRole('alert')).toContainText("None of this workspace's papers can be searched yet")
  await expect(refused.getByRole('button', { name: 'Retry' })).toBeVisible()

  const [chunk] = await (await request.get(`/api/papers/${paperId}/chunks?page=1`)).json()
  const sources = {
    whole_paper: false,
    sources: [{ label: 'C1', chunk_id: chunk.id, paper_id: paperId, page: 1, section: null, bbox: chunk.bbox }],
    notes: [{ label: 'N1', note_id: crypto.randomUUID(), paper_id: paperId, page: 1, provenance: 'llm' }],
    notes_used: 58,
    notes_total: 64,
  }
  await page.unrouteAll()
  await page.route('**/chat', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body:
            `event: sources\ndata: ${JSON.stringify(sources)}\n\n` +
            'event: token\ndata: {"text":"Trimmed [C1][N1]"}\n\n' +
            `event: error\ndata: ${JSON.stringify({ message: 'Stopped by the test.', retryable: false })}\n\n`,
        })
      : route.fallback(),
  )
  await question.fill('Trimmed?')
  await question.press('Enter')
  const trimmed = page.locator('article.chat-answer', { hasText: 'Trimmed?' })
  await expect(trimmed.getByRole('alert')).toContainText('Stopped by the test.')
  await expect(trimmed).toContainText('Using 58 of 64 notes (newest first)')
  await expect(trimmed.locator('.chat-sources').getByRole('button', { name: `N1 · AI · ${FIXTURE_TITLE} p.1` })).toBeVisible()
})
