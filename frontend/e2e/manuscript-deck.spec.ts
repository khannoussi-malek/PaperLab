import { randomUUID } from 'node:crypto'
import type { APIRequestContext, Page } from '@playwright/test'
import { addNote, expect, test } from './fixtures'

const QUOTE_BODY = 'deck highlight'
const QUOTE = `Quote for ${QUOTE_BODY}`

async function newManuscript(page: Page, workspaceId: string, title: string): Promise<string> {
  await page.goto(`/#/workspaces/${workspaceId}?tab=write`)
  await page.getByRole('button', { name: 'New manuscript' }).click()
  await page.getByLabel('Title').fill(title)
  await page.getByRole('radio', { name: 'IEEE conference' }).click()
  await page.getByRole('button', { name: 'Create' }).click()
  await expect(page).toHaveURL(/#\/manuscripts\/[0-9a-f-]{36}/)
  return /manuscripts\/([0-9a-f-]{36})/.exec(page.url())![1]
}

async function addToWorkspace(request: APIRequestContext, workspaceId: string, ...paperIds: string[]) {
  for (const id of paperIds) expect((await request.put(`/api/workspaces/${workspaceId}/papers/${id}`)).status()).toBe(204)
}

const deck = (page: Page) => page.locator('[aria-roledescription="paper deck"]')
const book = (page: Page) => page.locator('[aria-roledescription="paper book"]')

/** Narrow studios put Papers and PDF in one column as tabs: show the one named `name` (a no-op when it has its own column). */
async function showTab(page: Page, name: string) {
  const tab = page.getByRole('tab', { name, exact: true })
  if (await tab.count()) {
    await tab.click()
    await expect(tab).toHaveAttribute('aria-selected', 'true')
  }
}

// Keyboard only: the Papers column, a highlight inserted as a quote + \citep, compile, \cite{ completion, Cmd+K.
// Run wide (own Papers column) and at Playwright's default 1280x720 (Papers is a tab beside the PDF).
// 1920 leaves room for every column; at 1600 the studio first guesses wide and then measures narrow (remounting the deck), so that size is not used.
for (const size of [{ width: 1920, height: 1080 }, { width: 1280, height: 720 }]) {
  test(`Cite from the paper deck at ${size.width}px: open a paper, insert its highlight, compile, complete a key, jump to a label`, async ({
    page, request, workspaceId, paperId, tablePaperId,
  }) => {
    test.setTimeout(300_000)
    await page.setViewportSize(size)
    const wide = size.width >= 1920
    await addToWorkspace(request, workspaceId, paperId, tablePaperId)
    await addNote(request, paperId, 1, QUOTE_BODY)
    let manuscriptId = ''
    try {
      manuscriptId = await newManuscript(page, workspaceId, `E2E deck ${randomUUID().slice(0, 8)}`)
      const content = page.locator('.cm-content')

      // Cursor at the end of the abstract line (found by its text, not by counting lines), so the insert lands there.
      await content.locator('.cm-line', { hasText: 'Write your abstract here.' }).click()
      await page.keyboard.press('End')

      // The deck: Home, then right-arrow (at most once per paper) until the paper with the highlight is in front.
      if (wide) await expect(page.getByRole('region', { name: 'Papers' })).toBeVisible()
      else await expect(page.getByRole('tab', { name: 'Papers', exact: true })).toBeVisible()
      await showTab(page, 'Papers')
      await expect(deck(page)).toBeVisible()
      await deck(page).focus()
      await page.keyboard.press('Home')
      const status = page.locator('p[role=status][aria-live=polite]').filter({ hasText: /paper \d+ of \d+/ })
      await expect(status).toContainText('paper 1 of 2')
      for (let i = 0; i < 2; i++) {
        if (/1 highlight/.test((await status.textContent()) ?? '')) break
        await page.keyboard.press('ArrowRight')
        await expect(status).toContainText(`paper ${i + 2} of 2`)
      }
      await expect(status).toContainText('1 highlight')
      await page.keyboard.press('Enter')
      await expect(book(page)).toBeFocused()
      await expect(book(page).locator('[data-book-tab]')).toHaveCount(1)
      await page.keyboard.press('ArrowDown') // one item only: stays on the highlight
      await page.keyboard.press('i')

      // Focus is back in the editor and the text is the quote + a page-cited \citep.
      await expect(content).toContainText("``" + QUOTE + "''", { timeout: 15_000 })
      await expect(content).toContainText(/\\citep\[p\.~1\]\{[^}\s]+\}/)
      await expect(content).toBeFocused()

      // Compile: the PDF shows the quote and a reference list (the title's first words).
      await page.keyboard.press('ControlOrMeta+s')
      await showTab(page, 'PDF')
      const pdf = page.getByRole('region', { name: 'PDF preview' })
      await expect(pdf.locator('canvas').first()).toBeVisible({ timeout: 180_000 })
      await expect(pdf).toContainText(/Quote for deck high-?\s*light/, { timeout: 60_000 }) // the PDF may hyphenate the word
      await expect(pdf).toContainText(/PaperLab E2E/i, { timeout: 60_000 })
      const detail = await (await request.get(`/api/manuscripts/${manuscriptId}`)).json()
      expect(detail.compile_status).toBe('ok')

      // \cite{ completion offers the other paper. Type line by line, closing any popup before each newline.
      await content.click()
      await page.keyboard.press('ControlOrMeta+End')
      await page.keyboard.press('Enter')
      await page.keyboard.type('\\label{sec:deckjump}')
      await page.keyboard.press('Escape')
      await page.keyboard.press('Enter')
      await page.keyboard.type('\\cite{')
      const options = page.locator('.cm-tooltip-autocomplete [role=option]')
      await expect(options.filter({ hasText: 'PaperLab Table Fixture' })).toBeVisible({ timeout: 15_000 })
      await page.keyboard.press('Escape')

      // Cmd/Ctrl+K from the top of the file jumps to the label (retry until the new label is indexed).
      await page.keyboard.press('ControlOrMeta+Home')
      const option = page.getByRole('option', { name: /sec:deckjump/ })
      await expect(async () => {
        if (!(await page.getByPlaceholder(/Jump to a section/).isVisible())) await page.keyboard.press('ControlOrMeta+k')
        await page.getByPlaceholder(/Jump to a section/).fill('deckjump')
        await expect(option).toBeVisible({ timeout: 2_000 })
      }).toPass({ timeout: 20_000 })
      await option.click()
      await expect(page.locator('.cm-activeLine')).toContainText('\\label{sec:deckjump}')
    } finally {
      if (manuscriptId) await request.delete(`/api/manuscripts/${manuscriptId}`)
    }
  })
}

// Reduced motion: opening a paper and moving between its items are plain cuts, with no leaf in the DOM.
test('The paper book turns no leaf with reduced motion', async ({ page, request, workspaceId, paperId }) => {
  await page.setViewportSize({ width: 1920, height: 1080 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await addToWorkspace(request, workspaceId, paperId)
  await addNote(request, paperId, 1, 'first')
  await addNote(request, paperId, 2, 'second')
  let manuscriptId = ''
  try {
    manuscriptId = await newManuscript(page, workspaceId, `E2E deck still ${randomUUID().slice(0, 8)}`)
    const leaf = book(page).locator('[data-shade]') // only a turning leaf's faces carry it (deck/pageTurn.ts)
    await expect(page.getByRole('region', { name: 'Papers' })).toBeVisible()
    await expect(page.locator('p[role=status][aria-live=polite]').filter({ hasText: /paper 1 of 1/ })).toContainText('2 highlights')
    await deck(page).focus()
    await page.keyboard.press('Enter')
    await expect(book(page).locator('[data-book-tab]')).toHaveCount(2)
    await expect(leaf).toHaveCount(0)
    await page.keyboard.press('ArrowDown')
    await expect(book(page).locator('[data-book-tab][aria-current=true]')).toHaveAttribute('aria-label', /page 2/)
    await expect(leaf).toHaveCount(0)
    await page.keyboard.press('ArrowUp')
    await expect(book(page).locator('[data-book-tab][aria-current=true]')).toHaveAttribute('aria-label', /page 1/)
    await expect(leaf).toHaveCount(0)

    // Control: with motion allowed the same key does turn a leaf, so the marker above really would show one.
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    await page.keyboard.press('ArrowDown')
    await expect(leaf.first()).toBeAttached()
  } finally {
    if (manuscriptId) await request.delete(`/api/manuscripts/${manuscriptId}`)
  }
})
