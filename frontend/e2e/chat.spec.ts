import type { Locator, Page } from '@playwright/test'
import { addNote, ask, expect, openReader, pickChatModel, selectAllOf, selectText, test, type Rect } from './fixtures'

/** What `FakeLLM` always answers (backend `LLM_PROVIDER=fake`). */
const FAKE_ANSWER = 'Fake answer: the method is described here [C1].'
/** Faked responses follow the API for a paper without notes. */
const NO_NOTES = { notes: [], notes_used: 0, notes_total: 0 }

// Every answer here comes from this test's own connection, whatever the owner's default is.
test.beforeEach(async ({ page, llmConnection }) => {
  await pickChatModel(page, llmConnection.modelId)
})

/** Opens the reader on the Chat tab. */
async function openChat(page: Page, paperId: string) {
  await page.goto(`/#/papers/${paperId}?tab=chat`)
  await expect(page.getByRole('tab', { name: 'Chat' })).toHaveAttribute('aria-selected', 'true')
}

/** Selects from the very start of `start` to the very end of `end` (which may be a later sibling), then releases. */
async function selectFromStartToEnd(start: Locator, end: Locator) {
  const endHandle = await end.elementHandle()
  await start.evaluate((startNode, endNode) => {
    const range = document.createRange()
    range.setStart(startNode, 0)
    range.setEnd(endNode!, endNode!.childNodes.length)
    window.getSelection()!.removeAllRanges()
    window.getSelection()!.addRange(range)
  }, endHandle)
  await start.dispatchEvent('mouseup')
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

test('the question box regains focus once the answer is saved', async ({ page, paperId }) => {
  await openChat(page, paperId)
  const question = page.getByRole('textbox', { name: 'Question' })
  // page.keyboard, not the locator's fill()/press(): those refocus the element themselves and would
  // hide a focus loss that happens while the field is disabled mid-stream.
  await question.click()
  await page.keyboard.type('Does focus return?')
  await page.keyboard.press('Enter')
  await expect(page.locator('article.chat-answer[data-output-id]', { hasText: 'Does focus return?' })).toBeVisible()
  await expect(question).toBeFocused()
})

test('an answer streams in after its sources are shown, and is saved', async ({ page, request, paperId, llmConnection }) => {
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
  await expect(answer.locator('.chat-answer-footer')).toHaveText(`AI · fake:e2e-model · ${llmConnection.label} · prompt v4`)
  const saved = await (await request.get(`/api/papers/${paperId}/chat`)).json()
  expect(saved.map((a: { content: string }) => a.content)).toEqual([FAKE_ANSWER])
})

test('an empty chat offers starter questions that ask in one click, and Ask sends a typed question', async ({
  page,
  paperId,
}) => {
  await openChat(page, paperId)
  const heading = page.getByRole('heading', { name: 'Ask this paper' })
  await expect(heading).toBeVisible()
  const starters = page.getByRole('list', { name: 'Suggested questions' }).getByRole('button')
  await expect(starters).toHaveText(['Summarize the main contribution', 'What method do they use?', 'What are the limitations?'])

  await starters.filter({ hasText: 'What are the limitations?' }).click()
  await expect(page.locator('article.chat-answer[data-output-id] .chat-question')).toHaveText('What are the limitations?')
  await expect(heading).toHaveCount(0)

  await page.getByRole('textbox', { name: 'Question' }).fill('Typed question?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.locator('article.chat-answer[data-output-id] .chat-question')).toHaveText([
    'What are the limitations?',
    'Typed question?',
  ])
})

test("an answer's sources are small pills under its text, and its details wait behind hover", async ({
  page,
  request,
  paperId,
}) => {
  // The fixture paper is small enough to be sent whole, so a stream with separate sources is faked.
  const [chunk] = await (await request.get(`/api/papers/${paperId}/chunks?page=1`)).json()
  const longSection = 'A section heading long enough to run past the edge of the side panel'
  const sources = [
    { label: 'C1', chunk_id: chunk.id, paper_id: paperId, page: 1, section: 'Method', bbox: chunk.bbox },
    { label: 'C2', chunk_id: chunk.id, paper_id: paperId, page: 1, section: longSection, bbox: chunk.bbox },
  ]
  await page.route('**/chat', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body:
            `event: sources\ndata: ${JSON.stringify({ whole_paper: false, sources, ...NO_NOTES })}\n\n` +
            'event: token\ndata: {"text":"Two passages [C1] and [C2]."}\n\n' +
            `event: done\ndata: ${JSON.stringify({ output_id: '00000000-0000-4000-8000-000000000002', model: 'fake', connection_name: null, prompt_version: 1 })}\n\n`,
        })
      : route.fallback(),
  )
  await openChat(page, paperId)
  await page.getByRole('textbox', { name: 'Question' }).fill('Two sources?')
  await page.getByRole('textbox', { name: 'Question' }).press('Enter')

  const answer = page.locator('article.chat-answer', { hasText: 'Two sources?' })
  const list = answer.locator('.chat-sources')
  const pills = list.getByRole('button')
  await expect(pills).toHaveText(['C1', 'C2'])
  await expect(pills.nth(1)).toHaveAccessibleName(`Source 2: page 1, section “${longSection}”`)
  const textComesFirst = await answer
    .locator('.chat-answer-text')
    .evaluate((text, other) => (text.compareDocumentPosition(other!) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0, await list.elementHandle())
  expect(textComesFirst).toBe(true)

  // "C1" alone means nothing to a reader, so hovering a marker in the text says in words what it is.
  // Hovered top to bottom: each tooltip opens above its trigger, so the next trigger down is never under it.
  await glideTo(page, answer.locator('.chat-cite').first())
  await expect(page.getByRole('tooltip')).toContainText('Source 1: page 1, section “Method”')
  // The model and prompt version sit behind the AI mark instead of repeating under every answer.
  await glideTo(page, answer.locator('.chat-answer-footer'))
  await expect(page.getByRole('tooltip', { name: 'AI · fake · prompt v1' })).toBeVisible()
  // Pills explain themselves the same way, and moving to the next pill shows the next one's explanation.
  await glideTo(page, pills.nth(0))
  // Moving from C1's open (wide) tooltip onto its neighbour is the case that once kept showing C1.
  await expect(page.getByRole('tooltip', { name: /^Source 1: page 1/ })).toBeVisible()
  await glideTo(page, pills.nth(1))
  const explained = page.getByRole('tooltip')
  await expect(explained).toHaveCount(1) // the earlier ones have closed
  await expect(explained).toContainText(`Source 2: page 1, section “${longSection}”`)
  await expect(explained).toContainText('The AI used this passage. Click to see it in the paper.')
})

/**
 * Moves the mouse to an element's centre like a person would: many small moves with short pauses, then a rest.
 * Radix tooltips decide open/close from the pointer's path, and a few instant jumps don't look like one.
 */
async function glideTo(page: Page, target: Locator) {
  const box = (await target.boundingBox())!
  const [x, y] = [box.x + box.width / 2, box.y + box.height / 2]
  await page.mouse.move(x, y, { steps: 25 })
  await page.mouse.move(x + 1, y)
  await page.waitForTimeout(150) // ponytail: a human rest; tooltips open on pointer movement, not on a timer
}

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

  // A paper ingested before chat existed has no embeddings: the API refuses before streaming (409 paper_not_indexed).
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
  const source = { label: 'C1', chunk_id: chunk!.id, paper_id: paperId, page: 1, section: null, bbox: chunk!.bbox }
  await page.unrouteAll()
  await page.route('**/chat', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body:
            `event: sources\ndata: ${JSON.stringify({ whole_paper: true, sources: [source], ...NO_NOTES })}\n\n` +
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

test('clicking [C1] scrolls the paper to the cited chunk and flashes its rects', async ({ page, request, paperId }) => {
  await openChat(page, paperId)
  const answer = await ask(page, 'Where does the paper say it?')
  const firstPage = page.locator('.pdf-page[data-page="1"]')
  const flash = firstPage.locator('.chunk-flash')

  // Scroll the paper to its end, so page 1's chunk is out of view before the click.
  const firstLine = firstPage.locator('.textLayer span').first()
  await expect(firstLine).toBeVisible()
  await page.locator('section:has(> .pdf-page)').evaluate((pane) => pane.scrollTo({ top: pane.scrollHeight }))
  await expect(firstLine).not.toBeInViewport()

  await answer.locator('.chat-answer-text').getByRole('button', { name: /^Source 1: page 1/ }).first().click()

  await expect(flash.first()).toBeInViewport()
  // Same check as reader-render.spec.ts: the rect sits where PyMuPDF put the chunk, at the reader's 150% zoom.
  const [chunk] = await (await request.get(`/api/papers/${paperId}/chunks?page=1`)).json()
  const [x0, y0, x1, y1] = chunk.bbox[0] as Rect
  const scale = 1.5
  await expect
    .poll(async () => {
      const pageBox = await firstPage.boundingBox()
      const box = await flash.first().boundingBox()
      if (!pageBox || !box) return Number.POSITIVE_INFINITY
      return Math.max(
        Math.abs(box.x - (pageBox.x + x0 * scale)),
        Math.abs(box.y - (pageBox.y + y0 * scale)),
        Math.abs(box.width - (x1 - x0) * scale),
        Math.abs(box.height - (y1 - y0) * scale),
      )
    })
    .toBeLessThan(2)
  await expect(flash).toHaveCount(chunk.bbox.length)
  await expect(flash).toHaveCount(0, { timeout: 3_000 }) // it fades after about 1.5 s
})

test("clicking [N1] focuses the paper's note that the answer cites", async ({ page, request, paperId }) => {
  const note = await addNote(request, paperId, 1, 'My note for chat')
  // FakeLLM's paper answer cites only passages, so a stream citing the note is faked.
  const notes = [{ label: 'N1', note_id: note.id, paper_id: paperId, page: 1, provenance: 'human' }]
  await page.route('**/chat', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body:
            `event: sources\ndata: ${JSON.stringify({ whole_paper: true, sources: [], notes, notes_used: 1, notes_total: 1 })}\n\n` +
            'event: token\ndata: {"text":"As your note says [N1]."}\n\n' +
            `event: done\ndata: ${JSON.stringify({ output_id: '00000000-0000-4000-8000-000000000009', model: 'fake', connection_name: null, prompt_version: 2 })}\n\n`,
        })
      : route.fallback(),
  )
  await openChat(page, paperId)
  await page.locator('section:has(> .pdf-page)').evaluate((pane) => pane.scrollTo({ top: pane.scrollHeight }))
  await page.getByRole('textbox', { name: 'Question' }).fill('What did I note?')
  await page.getByRole('textbox', { name: 'Question' }).press('Enter')

  const answer = page.locator('article.chat-answer', { hasText: 'What did I note?' })
  await expect(answer.locator('.chat-sources').getByRole('button', { name: /^N1 · You/ })).toBeVisible()
  const highlight = page.locator(`.highlight[data-note-id="${note.id}"]`)
  await expect(highlight).not.toBeInViewport()
  await answer.locator('.chat-cite', { hasText: '[N1]' }).click()
  await expect(page.locator(`.highlight.active[data-note-id="${note.id}"]`)).toBeInViewport()
})

test('saving a passage of an answer makes an AI note on its cited chunk, and editing it marks it edited', async ({
  page,
  request,
  paperId,
}) => {
  // Notes sort by (page, y0, x0) (backend `reading_position`), so eight page-1 fillers above the cited chunk
  // (y0 110, per the fixture's first chunk) sort before the new AI note, pushing its card below the fold — a
  // real check that "scrolls to the new note" works, not one that would pass anyway with a single card in view.
  for (let i = 0; i < 8; i++) {
    const created = await request.post('/api/notes', {
      data: {
        body: `filler ${i}`,
        anchor: { paper_id: paperId, page: 1, bbox: [[72, 10 + i * 10, 300, 20 + i * 10]], quoted_text: `filler quote ${i}` },
      },
    })
    expect(created.ok()).toBe(true)
  }

  await openChat(page, paperId)
  const answer = await ask(page, 'What anchors a note?')
  const [saved] = await (await request.get(`/api/papers/${paperId}/chat`)).json()

  await selectAllOf(answer.locator('.chat-answer-text'))
  await page.getByRole('button', { name: 'Save as note' }).click()

  await expect(page.getByRole('tab', { name: 'Notes' })).toHaveAttribute('aria-selected', 'true')
  await expect.poll(async () => (await (await request.get(`/api/papers/${paperId}/notes`)).json()).length).toBe(9)
  const notes = await (await request.get(`/api/papers/${paperId}/notes`)).json()
  const note = notes.find((n: { provenance: string }) => n.provenance === 'llm')
  const [chunk] = await (await request.get(`/api/papers/${paperId}/chunks?page=1`)).json()
  // The body keeps the raw [C1] marker: the API only accepts a verbatim slice of the stored answer.
  expect([note.provenance, note.source_id, note.body]).toEqual(['llm', saved.id, FAKE_ANSWER])
  expect([note.anchors[0].page, note.anchors[0].bbox]).toEqual([1, chunk.bbox])

  const card = page.locator(`article.note[data-note-id="${note.id}"]`)
  await expect(card).toBeInViewport()
  await expect(card.locator('.provenance-badge')).toHaveText('AI')

  await card.getByRole('button', { name: 'Edit' }).click()
  await card.getByRole('textbox', { name: 'Edit note' }).fill('In my own words now.')
  await card.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(card.locator('.provenance-badge')).toHaveText('AI · edited')
  await page.reload()
  await expect(page.locator(`article.note[data-note-id="${note.id}"] .provenance-badge`)).toHaveText('AI · edited')
})

test('a chat history taller than the panel scrolls inside the panel, never the whole page', async ({ page, paperId }) => {
  // Enough saved answers to overflow the panel, faked so the test doesn't ask the model a dozen times.
  const answers = Array.from({ length: 12 }, (_, i) => ({
    id: `00000000-0000-4000-8000-0000000001${String(i).padStart(2, '0')}`,
    question: `Question ${i}?`,
    content: 'An answer long enough to take a few lines in the side panel, so that twelve of them overflow it.',
    model: 'fake',
    connection_name: null,
    prompt_version: 1,
    created_at: '2026-09-14T00:00:00Z',
    whole_paper: true,
    sources: [],
    ...NO_NOTES,
  }))
  await page.route('**/chat', (route) => (route.request().method() === 'GET' ? route.fulfill({ json: answers }) : route.fallback()))
  await openChat(page, paperId)
  await expect(page.locator('article.chat-answer')).toHaveCount(12)

  const list = page.locator('article.chat-answer').first().locator('..')
  expect(await list.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true)
  // Screen-reader-only labels are absolutely positioned: they must not escape the list and stretch the page.
  expect(await page.evaluate(() => document.scrollingElement!.scrollHeight - window.innerHeight)).toBe(0)
})

test('a passage with no citation nearby cannot be saved, and the button says why', async ({ page, paperId }) => {
  // The fake model always cites [C1], so this one history answer, with no marker at all, is faked.
  await page.route('**/chat', (route) =>
    route.request().method() === 'GET'
      ? route.fulfill({
          json: [
            {
              id: '00000000-0000-4000-8000-000000000001',
              question: 'Uncited?',
              content: 'An answer that cites nothing.',
              model: 'fake',
              connection_name: null,
              prompt_version: 1,
              created_at: '2026-09-13T00:00:00Z',
              whole_paper: true,
              sources: [],
              ...NO_NOTES,
            },
          ],
        })
      : route.fallback(),
  )
  await openChat(page, paperId)
  await selectAllOf(page.locator('article.chat-answer .chat-answer-text'))

  const save = page.getByRole('button', { name: 'Save as note' })
  await expect(save).toBeDisabled()
  await page.locator('.save-as-note span[tabindex="0"]').focus()
  await expect(page.getByRole('tooltip')).toHaveText('Include a cited passage [C…] to anchor this note')
})

test('selecting past the answer into its footer still saves just the answer text', async ({ page, request, paperId }) => {
  // A triple-click or a drag that overshoots into the footer must still anchor to the answer's own text.
  await openChat(page, paperId)
  const answer = await ask(page, 'What anchors a note?')
  await selectFromStartToEnd(answer.locator('.chat-answer-text'), answer.locator('.chat-answer-footer'))

  await page.getByRole('button', { name: 'Save as note' }).click()
  await expect.poll(async () => (await (await request.get(`/api/papers/${paperId}/notes`)).json()).length).toBe(1)
  const [note] = await (await request.get(`/api/papers/${paperId}/notes`)).json()
  expect(note.body).toBe(FAKE_ANSWER)
})

test('extending a selection with Shift+ArrowLeft changes what gets saved', async ({ page, request, paperId }) => {
  await openChat(page, paperId)
  const answer = await ask(page, 'What anchors a note?')
  const text = answer.locator('.chat-answer-text')
  await selectAllOf(text)
  // Real Shift+ArrowLeft only adjusts a page selection with caret browsing on (off by default, incl. headless
  // Chromium), so this drives the same standard Selection.extend() call the browser makes internally: move the
  // focus, which selectAllOf left at the very end, back by one character (the trailing "."), anchor unchanged.
  await text.evaluate((node) => {
    const selection = window.getSelection()!
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT)
    let last: Text | null = null
    for (let n = walker.nextNode(); n; n = walker.nextNode()) last = n as Text
    selection.extend(last!, (last!.textContent?.length ?? 1) - 1)
  })

  await page.getByRole('button', { name: 'Save as note' }).click()
  await expect.poll(async () => (await (await request.get(`/api/papers/${paperId}/notes`)).json()).length).toBe(1)
  const [note] = await (await request.get(`/api/papers/${paperId}/notes`)).json()
  expect(note.body).toBe(FAKE_ANSWER.slice(0, -1))
})

test('a failed promote shows a readable message next to the Save button', async ({ page, paperId }) => {
  await openChat(page, paperId)
  const answer = await ask(page, 'What anchors a note?')
  await page.route('**/api/notes/promote', (route) =>
    route.fulfill({ status: 422, contentType: 'application/json', body: '{"detail":"body_not_in_output"}' }),
  )

  await selectAllOf(answer.locator('.chat-answer-text'))
  await page.getByRole('button', { name: 'Save as note' }).click()

  const message = page.getByRole('alert').filter({ hasText: "doesn't match the saved answer" })
  await expect(message).toBeInViewport()
  // The button stays up so the user can select again without losing their place.
  await expect(page.getByRole('button', { name: 'Save as note' })).toBeVisible()
})
