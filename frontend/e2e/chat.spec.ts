import type { Page } from '@playwright/test'
import { expect, openReader, selectText, test } from './fixtures'

/** What `FakeLLM` always answers (backend `LLM_PROVIDER=fake`). */
const FAKE_ANSWER = 'Fake answer: the method is described here [C1].'

/** Opens the reader on the Chat tab. */
async function openChat(page: Page, paperId: string) {
  await page.goto(`/#/papers/${paperId}?tab=chat`)
  await expect(page.getByRole('tab', { name: 'Chat' })).toHaveAttribute('aria-selected', 'true')
}

/** Asks with Enter, and waits until the answer is saved: only a saved answer has `data-output-id`. */
async function ask(page: Page, question: string) {
  await page.getByRole('textbox', { name: 'Question' }).fill(question)
  await page.getByRole('textbox', { name: 'Question' }).press('Enter')
  const answer = page.locator('article.chat-answer[data-output-id]', { hasText: question })
  await expect(answer.locator('.chat-answer-footer')).toContainText('AI · ')
  return answer
}

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
  // A CSS locator, not getByRole: a hidden `<aside>` drops out of the accessibility tree, so
  // getByRole('complementary', …) would match zero elements and toBeHidden() would pass on a panel
  // that was never mounted at all. toBeAttached() first proves it is still in the DOM.
  const notesPanel = page.locator('aside[aria-label="Notes"]')
  await expect(notesPanel).toBeAttached()
  await expect(notesPanel).toBeHidden()

  // The note composer lives on the Notes tab, so a new selection brings it back.
  await expect(line).toBeVisible()
  await selectText(line)
  await expect(notesTab).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('textbox', { name: 'Note' })).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`#/papers/${paperId}$`))
})

test('an answer streams in after its sources are shown, and is saved', async ({ page, request, paperId }) => {
  await openChat(page, paperId)
  // At every DOM change, note whether the answer has text yet and whether its sources were already on screen.
  await page.evaluate(() => {
    const seen: { sources: boolean; text: boolean }[] = []
    Object.assign(window, { chatOrder: seen })
    new MutationObserver(() => {
      const answer = document.querySelector('article.chat-answer')
      seen.push({
        sources: answer?.querySelector('.chat-sources li') != null,
        text: (answer?.querySelector('.chat-answer-text')?.textContent ?? '') !== '',
      })
    }).observe(document.body, { childList: true, subtree: true, characterData: true })
  })

  const answer = await ask(page, 'What anchors a note?')

  const order = await page.evaluate(() => (window as unknown as { chatOrder: { sources: boolean; text: boolean }[] }).chatOrder)
  const firstText = order.findIndex((snapshot) => snapshot.text)
  expect(firstText).toBeGreaterThan(-1)
  expect(order[firstText].sources).toBe(true)

  // The fixture paper is small, so the whole paper is the context (spec §3.9).
  const chunks = await (await request.get(`/api/papers/${paperId}/chunks`)).json()
  await expect(answer.locator('.chat-sources')).toHaveText(`Whole paper · ${chunks.length} chunks`)
  // FakeLLM's fixed answer, streamed with the marker split into "[C" and "1]".
  await expect(answer.locator('.chat-answer-text')).toHaveText(FAKE_ANSWER)
  await expect(answer.locator('.chat-cite')).toHaveText(['[C1]'])
  await expect(answer.locator('.chat-answer-footer')).toHaveText('AI · fake · prompt v1')
  const saved = await (await request.get(`/api/papers/${paperId}/chat`)).json()
  expect(saved.map((a: { content: string }) => a.content)).toEqual([FAKE_ANSWER])
})

test('past questions and answers reload with the paper, oldest first', async ({ page, paperId }) => {
  await openChat(page, paperId)
  await ask(page, 'First question?')
  await ask(page, 'Second question?')
  await expect(page.locator('article.chat-answer .chat-question')).toHaveText(['First question?', 'Second question?'])

  await page.reload()
  await expect(page.locator('article.chat-answer .chat-question')).toHaveText(['First question?', 'Second question?'])
  await expect(page.locator('article.chat-answer .chat-answer-text')).toHaveText([FAKE_ANSWER, FAKE_ANSWER])
})

test('a refused question offers Re-index, and a broken stream keeps its text and offers Retry', async ({
  page,
  request,
  paperId,
}) => {
  await openChat(page, paperId)
  const question = page.getByRole('textbox', { name: 'Question' })

  // A paper ingested before M4 has no embeddings: the API refuses before streaming (409 paper_not_indexed).
  // The real stack only has indexed papers, so this one response is faked.
  await page.route('**/chat', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 409, contentType: 'application/json', body: '{"detail":"paper_not_indexed"}' })
      : route.fallback(),
  )
  await question.fill('Refused?')
  await question.press('Enter')
  const refused = page.locator('article.chat-answer', { hasText: 'Refused?' })
  await expect(refused.getByRole('alert')).toContainText('no search index yet')
  const [before] = await (await request.get(`/api/papers/${paperId}/chunks?page=1`)).json()
  await refused.getByRole('button', { name: 'Re-index' }).click()
  await expect(refused.getByRole('alert')).toContainText('Re-indexing started')
  // POST /reingest only enqueues the job, so `ready` alone can be the pre-reindex status. replace_chunks
  // always issues new UUIDs, so wait for `ready` and a changed first chunk id together.
  let chunk
  await expect
    .poll(
      async () => {
        const paper = await (await request.get(`/api/papers/${paperId}`)).json()
        ;[chunk] = await (await request.get(`/api/papers/${paperId}/chunks?page=1`)).json()
        return paper.status === 'ready' && chunk.id !== before.id
      },
      { timeout: 30_000 },
    )
    .toBe(true)

  // The model goes away mid-answer: the partial text stays, nothing is saved, and Retry asks again for real.
  const source = { label: 'C1', chunk_id: chunk!.id, page: 1, section: null, bbox: chunk!.bbox }
  await page.unrouteAll()
  await page.route('**/chat', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body:
            `event: sources\ndata: ${JSON.stringify({ whole_paper: true, sources: [source] })}\n\n` +
            'event: token\ndata: {"text":"Partial answer [C"}\n\n' +
            `event: error\ndata: ${JSON.stringify({ message: "Can't reach Ollama at http://host.docker.internal:11434", retryable: true })}\n\n`,
        })
      : route.fallback(),
  )
  await question.fill('Broken?')
  await question.press('Enter')
  const broken = page.locator('article.chat-answer', { hasText: 'Broken?' })
  await expect(broken.getByRole('alert')).toContainText("Can't reach Ollama")
  await expect(broken.locator('.chat-answer-text')).toHaveText('Partial answer [C')
  expect(await (await request.get(`/api/papers/${paperId}/chat`)).json()).toEqual([])

  await page.unrouteAll()
  await broken.getByRole('button', { name: 'Retry' }).click()
  await expect(broken.locator('.chat-answer-footer')).toContainText('AI · ')
  await expect(broken.getByRole('alert')).toHaveCount(0)
})
