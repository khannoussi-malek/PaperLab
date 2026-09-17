import type { Locator, Page } from '@playwright/test'
import { FIXTURE_FILE, expect, openReader, removePaperAndNotes, selectText, test } from './fixtures'

/** `enter` is tw-animate-css's entrance keyframe; `none` means the element doesn't animate. */
const animationOf = (locator: Locator) => locator.evaluate((element) => getComputedStyle(element).animationName)

const libraryRow = (page: Page, paperId: string) =>
  page.locator('.paper-row').filter({ has: page.locator(`a[href="#/papers/${paperId}"]`) })

/** Starts recording the paper ids of library rows whose entrance animation starts; returns a reader of that record. */
async function recordRowEntrances(page: Page): Promise<() => Promise<string[]>> {
  await page.evaluate(() => {
    const started: string[] = []
    Object.assign(window, { rowEntrances: started })
    document.addEventListener('animationstart', (event) => {
      const row = event.target instanceof Element && event.target.matches('.paper-row') ? event.target : null
      const href = row?.querySelector('a')?.getAttribute('href')
      if (href) started.push(href.replace('#/papers/', ''))
    })
  })
  return () => page.evaluate(() => (window as unknown as { rowEntrances: string[] }).rowEntrances)
}

/** Selects page 1's first line, saves it as a note, and returns the new card. */
async function saveNote(page: Page, line: Locator, body: string) {
  await selectText(line)
  await page.getByRole('textbox', { name: 'Note' }).fill(body)
  await page.getByRole('button', { name: 'Save note' }).click()
  const card = page.locator('article.note', { hasText: body })
  await expect(card).toBeVisible()
  return card
}

/** Faked chat responses follow the API for a paper without notes. */
const NO_NOTES = { notes: [], notes_used: 0, notes_total: 0 }

/** A chat stream that stops after its first words, so the live answer stays on screen (nothing gets saved). */
const unfinishedStream = (paperId: string) => (route: Parameters<Parameters<Page['route']>[1]>[0]) =>
  route.request().method() === 'POST'
    ? route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: `event: sources\ndata: ${JSON.stringify({ whole_paper: true, sources: [], ...NO_NOTES })}\n\nevent: token\ndata: {"text":"Partial for ${paperId}"}\n\n`,
      })
    : route.fallback()

test.describe('with motion allowed', () => {
  test.use({ reducedMotion: 'no-preference' })

  test('the reader, the note composer, a new note card, the hover card and a shown tab animate in', async ({
    page,
    paperId,
  }) => {
    const line = await openReader(page, paperId)
    expect(await animationOf(page.locator('.reader'))).toBe('enter')

    await selectText(line)
    expect(await animationOf(page.locator('form:has(textarea[aria-label="Note"])'))).toBe('enter')
    await page.getByRole('textbox', { name: 'Note' }).fill('fresh note')
    await page.getByRole('button', { name: 'Save note' }).click()
    const card = page.locator('article.note', { hasText: 'fresh note' })
    await expect(card).toBeVisible()
    expect(await animationOf(card)).toBe('enter')

    await line.hover()
    await expect(page.locator('.note-hover-card')).toBeVisible()
    expect(await animationOf(page.locator('.note-hover-card'))).toBe('enter')

    await page.getByRole('tab', { name: 'Chat' }).click()
    expect(await animationOf(page.getByRole('tabpanel', { name: 'Chat' }))).toBe('enter')

    // The page's canvas fades in once it has drawn, instead of flashing from blank.
    const canvas = page.locator('.pdf-page[data-page="1"] canvas')
    expect(await canvas.evaluate((element) => getComputedStyle(element).transitionProperty)).toContain('opacity')
    await expect.poll(() => canvas.evaluate((element) => getComputedStyle(element).opacity)).toBe('1')
  })

  test('notes and answers already saved do not animate; only new ones do', async ({ page, paperId }) => {
    const old = '2026-01-01T00:00:00Z'
    await page.route('**/api/papers/*/notes', (route) =>
      route.request().method() === 'GET'
        ? route.fulfill({
            json: [
              {
                id: '00000000-0000-4000-8000-000000000501',
                body: 'written last month',
                provenance: 'human',
                color: '#facc15',
                source_id: null,
                created_at: old,
                updated_at: old,
                anchors: [{ paper_id: paperId, page: 1, bbox: [[72, 400, 300, 412]], quoted_text: 'old quote' }],
              },
            ],
          })
        : route.fallback(),
    )
    await page.route('**/chat', (route) =>
      route.request().method() === 'GET'
        ? route.fulfill({
            json: [{ id: '00000000-0000-4000-8000-000000000502', question: 'Asked before?', content: 'Yes.', model: 'fake', connection_name: null, prompt_version: 1, created_at: old, whole_paper: true, sources: [], ...NO_NOTES }],
          })
        : unfinishedStream(paperId)(route),
    )
    await openReader(page, paperId)
    expect(await animationOf(page.locator('article.note', { hasText: 'written last month' }))).toBe('none')

    await page.getByRole('tab', { name: 'Chat' }).click()
    expect(await animationOf(page.locator('article.chat-answer', { hasText: 'Asked before?' }))).toBe('none')
    await page.getByRole('textbox', { name: 'Question' }).fill('Asked now?')
    await page.getByRole('textbox', { name: 'Question' }).press('Enter')
    const live = page.locator('article.chat-answer', { hasText: 'Asked now?' })
    await expect(live).toBeVisible()
    expect(await animationOf(live)).toBe('enter')
  })

  test('library rows stay still on load and while they keep matching, and fade in once when the search brings them back', async ({
    page,
    paperId,
  }) => {
    await page.goto('/')
    const row = libraryRow(page, paperId)
    expect(await animationOf(row)).toBe('none')
    const started = await recordRowEntrances(page)

    const search = page.getByRole('searchbox', { name: 'Search papers' })
    await search.fill('paperlab')
    await expect(row).toBeVisible()
    expect(await animationOf(row)).toBe('none')

    await search.fill('no paper is called this')
    expect(await animationOf(page.locator('.no-matches'))).toBe('enter')
    expect(await animationOf(page.locator('.search-count > span'))).toBe('enter')

    await search.fill('')
    await expect.poll(started).toContain(paperId)
    // Once played, the fade is dropped, so a panel shown again (a workspace tab) doesn't replay it.
    await expect.poll(() => animationOf(row)).toBe('none')
  })

  test('a paper uploaded after a search does not fade in: only the search brings rows back with a fade', async ({
    page,
    request,
  }) => {
    await page.goto('/')
    const search = page.getByRole('searchbox', { name: 'Search papers' })
    await search.fill('no paper is called this')
    await search.fill('')
    const started = await recordRowEntrances(page)

    const [uploaded] = await Promise.all([
      page.waitForResponse((r) => r.url().endsWith('/api/papers') && r.request().method() === 'POST'),
      page.locator('input[type="file"]').setInputFiles(FIXTURE_FILE),
    ])
    const { id } = await uploaded.json()
    try {
      await expect(libraryRow(page, id)).toBeVisible()
      // A row's fade starts within 240 ms of it appearing (its stagger delay); give it well over that.
      await page.waitForTimeout(800)
      expect(await started()).not.toContain(id)
    } finally {
      await removePaperAndNotes(request, id)
    }
  })

  test('filter chips shrink slightly while pressed', async ({ page, paperId }) => {
    await openReader(page, paperId)
    const chip = page.getByRole('group', { name: 'Show notes from' }).getByRole('button').first()
    const box = (await chip.boundingBox())!
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.down()
    await expect.poll(() => chip.evaluate((element) => getComputedStyle(element).scale)).toBe('0.97')
    await page.mouse.up()
    await expect.poll(() => chip.evaluate((element) => getComputedStyle(element).scale)).not.toBe('0.97')
  })
})

test.describe('with the OS set to reduce motion', () => {
  test.use({ reducedMotion: 'reduce' })

  test('nothing animates in', async ({ page, paperId }) => {
    const line = await openReader(page, paperId)
    expect(await animationOf(page.locator('.reader'))).toBe('none')
    const card = await saveNote(page, line, 'still note')
    expect(await animationOf(card)).toBe('none')
    await line.hover()
    await expect(page.locator('.note-hover-card')).toBeVisible()
    expect(await animationOf(page.locator('.note-hover-card'))).toBe('none')
    await page.getByRole('tab', { name: 'Chat' }).click()
    expect(await animationOf(page.getByRole('tabpanel', { name: 'Chat' }))).toBe('none')
  })

  test('library rows brought back by the search do not fade in', async ({ page, paperId }) => {
    await page.goto('/')
    const search = page.getByRole('searchbox', { name: 'Search papers' })
    await search.fill('no paper is called this')
    expect(await animationOf(page.locator('.no-matches'))).toBe('none')
    await search.fill('')
    const row = libraryRow(page, paperId)
    await expect(row).toBeVisible()
    expect(await animationOf(row)).toBe('none')
  })
})
