import type { APIRequestContext, Page } from '@playwright/test'
import { FIXTURE_TITLE, ask, expect, pickChatModel, selectAllOf, test } from './fixtures'

// Parallel-safe (D51): its own papers and workspace, every note found by its own id, no setting changed. A note that
// ends up on no paper isn't found by the paper fixtures' cleanup, so `cleanupNote` deletes it.

/** What `FakeLLM` answers a question asking for notes (backend `FAKE_NOTES_ANSWER`). */
const FIRST_NOTE = 'The method anchors every note on a passage [C1].'
const SECOND_NOTE = 'Keep one idea per note.'
const CLOSING = 'Both come from the method section [C1].'
const QUESTION = 'Create notes to help me understand this paper'

type SavedNote = { index: number; note_id: string; paper_ids: string[] }

// Every answer here comes from this test's own connection, whatever the owner's default is.
test.beforeEach(async ({ page, llmConnection }) => {
  await pickChatModel(page, llmConnection.modelId)
})

/** The saved suggestions of the one answer in a chat's history. */
async function savedNotes(request: APIRequestContext, historyUrl: string): Promise<SavedNote[]> {
  const [answer] = await (await request.get(historyUrl)).json()
  return answer.saved_notes
}

/** Holds the paper chat's history reads until `release()`: the answer's live copy then stays on screen after it ends. */
async function holdHistory(page: Page, paperId: string): Promise<() => void> {
  let release = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route(`**/api/papers/${paperId}/chat`, async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await held
    return route.fallback()
  })
  return release
}

test('a suggested note saves with a click, leaves its paper through Papers, and stays saved', async ({
  page,
  request,
  paperId,
  cleanupNote,
}) => {
  await page.goto(`/#/papers/${paperId}?tab=chat`)
  await expect(page.getByRole('heading', { name: 'Ask this paper' })).toBeVisible() // the empty history has loaded
  const release = await holdHistory(page, paperId)

  // 1. Two cards as it streams, and Save stays off until the saved answer is listed.
  await page.getByRole('textbox', { name: 'Question' }).fill(QUESTION)
  await page.getByRole('textbox', { name: 'Question' }).press('Enter')
  const live = page.locator('article.chat-answer:not([data-output-id])')
  await expect(live.locator('.suggested-note')).toHaveCount(2)
  const liveSaves = live.getByRole('button', { name: 'Save', exact: true })
  await expect(liveSaves.first()).toBeDisabled()
  await expect(live.locator('.chat-answer-footer')).toContainText('AI · ') // done: saved on the server, not listed yet
  await expect(liveSaves.first()).toBeDisabled()
  await expect(liveSaves.last()).toBeDisabled()
  release()

  // 2. Save the first: the model's own words, in the Notes tab with the AI badge and a highlight.
  const cards = page.locator('article.chat-answer[data-output-id]', { hasText: QUESTION }).locator('.suggested-note')
  await expect(cards).toHaveCount(2)
  await expect(cards.nth(0)).toContainText(FIRST_NOTE)
  await expect(cards.nth(1)).toContainText(SECOND_NOTE)
  await cards.nth(0).getByRole('button', { name: 'Save', exact: true }).click()
  await expect(cards.nth(0)).toContainText('Saved · Open')
  const [saved] = await savedNotes(request, `/api/papers/${paperId}/chat`)
  cleanupNote(saved.note_id)
  expect(saved).toEqual({ index: 0, note_id: saved.note_id, paper_ids: [paperId] })
  const onPaper: { id: string; body: string; provenance: string }[] = await (
    await request.get(`/api/papers/${paperId}/notes`)
  ).json()
  expect(onPaper.find((note) => note.id === saved.note_id)).toMatchObject({ body: FIRST_NOTE, provenance: 'llm' })
  await page.getByRole('tab', { name: 'Notes' }).click()
  const card = page.locator(`article.note[data-note-id="${saved.note_id}"]`)
  await expect(card.locator('.provenance-badge')).toHaveText('AI')
  await expect(page.locator(`.highlight[data-note-id="${saved.note_id}"]`).first()).toBeAttached()

  // 3. Papers: untick this paper. The dialog warns about the highlight; saving takes the card off the panel.
  await card.getByRole('button', { name: 'Papers' }).click()
  const dialog = page.getByRole('dialog', { name: 'Papers' })
  const option = dialog.locator(`[data-paper-id="${paperId}"]`)
  await expect(option).toHaveAttribute('aria-checked', 'true')
  await option.click()
  await expect(option).toHaveAttribute('aria-checked', 'false')
  await expect(dialog.locator('.unlink-warning')).toHaveText(`Its highlight on p. 1 in ${FIXTURE_TITLE} will be removed.`)
  await dialog.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(card).toHaveCount(0)
  await expect(page.getByRole('status').filter({ hasText: 'Moved to Notes' })).toBeVisible()

  // 4. The Notes page lists it under No paper.
  await page.goto('/#/notes?paper=none')
  const loose = page.locator(`article.note[data-note-id="${saved.note_id}"]`)
  await expect(loose).toContainText(FIRST_NOTE)
  await expect(loose).toContainText('No paper')

  // 5. Back in the reader's chat, the first card still says Saved, and Open now goes to No paper.
  await page.goto(`/#/papers/${paperId}?tab=chat`)
  const again = page.locator('article.chat-answer[data-output-id] .suggested-note')
  await expect(again.nth(0)).toContainText('Saved · Open')
  await expect(again.nth(0).getByRole('link', { name: 'Open' })).toHaveAttribute('href', '#/notes?paper=none')
  await expect(again.nth(1).getByRole('button', { name: 'Save', exact: true })).toBeEnabled()
})

test('in workspace chat, a suggested note that cites nothing saves on no paper', async ({
  page,
  request,
  paperId,
  workspaceId,
  cleanupNote,
}) => {
  test.slow() // workspace chat retrieves: the first question can pay for loading the search model
  expect((await request.put(`/api/workspaces/${workspaceId}/papers/${paperId}`)).status()).toBe(204)
  await page.goto(`/#/workspaces/${workspaceId}?tab=chat`)

  const answer = await ask(page, 'Write notes on these papers', 45_000)
  const second = answer.locator('.suggested-note').nth(1)
  await expect(second).toContainText(SECOND_NOTE)
  await second.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(second).toContainText('Saved · Open')

  const [saved] = await savedNotes(request, `/api/workspaces/${workspaceId}/chat`)
  cleanupNote(saved.note_id)
  expect(saved).toEqual({ index: 1, note_id: saved.note_id, paper_ids: [] })
  await expect(second.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '#/notes?paper=none')
  await page.goto('/#/notes?paper=none')
  await expect(page.locator(`article.note[data-note-id="${saved.note_id}"]`)).toContainText(SECOND_NOTE)
})

test('Save as note maps to the stored answer inside a card and after the cards', async ({ page, request, paperId }) => {
  await page.goto(`/#/papers/${paperId}?tab=chat`)
  const answer = await ask(page, QUESTION)

  // The whole first card, label and Save included: only the note's own text is saved.
  await selectAllOf(answer.locator('.suggested-note').nth(0))
  await page.getByRole('button', { name: 'Save as note' }).click()
  await expect(page.getByRole('tab', { name: 'Notes' })).toHaveAttribute('aria-selected', 'true')
  // The closing line, after both cards: their labels and buttons must not shift where it starts.
  await page.getByRole('tab', { name: 'Chat' }).click()
  await selectAllOf(answer.locator('.chat-answer-text > p').last())
  await page.getByRole('button', { name: 'Save as note' }).click()
  await expect(page.getByRole('tab', { name: 'Notes' })).toHaveAttribute('aria-selected', 'true')

  const bodies = async () =>
    ((await (await request.get(`/api/papers/${paperId}/notes`)).json()) as { body: string }[]).map((n) => n.body).sort()
  await expect.poll(bodies).toEqual([CLOSING, FIRST_NOTE].sort())
})
