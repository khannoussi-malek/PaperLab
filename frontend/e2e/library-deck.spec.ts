import type { Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { addNote, expect, test } from './fixtures'

const NOTE_BODY = 'library deck highlight'
const deck = (page: Page) => page.locator('[aria-roledescription="paper deck"]')
const book = (page: Page) => page.locator('[aria-roledescription="paper book"]')
const status = (page: Page) => page.locator('p[role=status][aria-live=polite]').filter({ hasText: /paper \d+ of \d+/ })
const viewSwitch = (page: Page) => page.getByRole('group', { name: 'Show papers as' })
const rowOf = (page: Page, id: string) => page.locator('.paper-row').filter({ has: page.locator(`a[href="#/papers/${id}"]`) })

test('Browse the library as a deck: search narrows it, keys open a paper, o opens the reader, List keeps the search, the choice survives a reload', async ({
  page, request, paperId, secondPaperId, tablePaperId,
}) => {
  test.setTimeout(120_000)
  await addNote(request, paperId, 1, NOTE_BODY)
  // A title of their own: the stack may hold other fixture papers with the shared title.
  const unique = `Deckfind ${randomUUID().slice(0, 8)}`
  for (const id of [paperId, secondPaperId]) expect((await request.patch(`/api/papers/${id}`, { data: { title: unique } })).ok()).toBe(true)
  await page.goto('/#/')
  const search = page.getByRole('searchbox', { name: 'Search papers' })
  await search.fill(unique)
  await expect(rowOf(page, paperId)).toBeVisible()
  await expect(rowOf(page, secondPaperId)).toBeVisible()
  await expect(rowOf(page, tablePaperId)).toHaveCount(0)

  // Deck: the same two papers, no more.
  const counts = page.waitForResponse((r) => r.url().includes('/api/papers/note-counts')) // the highlight count arrives after the deck
  await viewSwitch(page).getByRole('button', { name: 'Deck' }).click()
  await expect(deck(page)).toBeVisible()
  await expect(status(page)).toContainText('of 2')
  await counts

  // Arrows until the paper with the highlight is in front, Enter opens its book.
  await deck(page).focus()
  await page.keyboard.press('Home')
  await expect(status(page)).toContainText('paper 1 of 2')
  for (let i = 0; i < 2; i++) {
    if (/1 highlight/.test((await status(page).textContent()) ?? '')) break
    await page.keyboard.press('ArrowRight')
    await expect(status(page)).toContainText(`paper ${i + 2} of 2`)
  }
  await expect(status(page)).toContainText('1 highlight')
  await page.keyboard.press('ArrowLeft') // ←/→ both move; step back and forth to the same paper
  await page.keyboard.press('ArrowRight')
  await expect(status(page)).toContainText('1 highlight')
  await page.keyboard.press('Enter')
  await expect(book(page)).toBeFocused()
  const tab = book(page).locator('[data-book-tab]')
  await expect(tab).toHaveCount(1)
  await expect(tab.first()).toHaveAttribute('aria-label', /^Your highlight, page 1/)
  await expect(book(page)).toContainText(NOTE_BODY)

  // o opens the reader in a new tab, at the note.
  const popup = page.waitForEvent('popup')
  await page.keyboard.press('o')
  expect((await popup).url()).toContain(`/papers/${paperId}`)
  await (await popup).close()

  // Esc closes the book; the deck is back with its search intact.
  await page.keyboard.press('Escape')
  await expect(deck(page)).toBeVisible()
  await expect(status(page)).toContainText('of 2')

  // List again: same search text, same rows.
  await viewSwitch(page).getByRole('button', { name: 'List' }).click()
  await expect(search).toHaveValue(unique)
  await expect(rowOf(page, paperId)).toBeVisible()
  await expect(rowOf(page, secondPaperId)).toBeVisible()
  await expect(rowOf(page, tablePaperId)).toHaveCount(0)

  // The choice is remembered across a reload.
  await viewSwitch(page).getByRole('button', { name: 'Deck' }).click()
  await page.reload()
  await expect(deck(page)).toBeVisible()
  await expect(viewSwitch(page).getByRole('button', { name: 'Deck' })).toHaveAttribute('aria-pressed', 'true')
})

test("A workspace's papers tab shows only the tagged papers as a deck", async ({ page, request, paperId, secondPaperId, workspaceId }) => {
  for (const id of [paperId, secondPaperId]) expect((await request.put(`/api/workspaces/${workspaceId}/papers/${id}`)).ok()).toBe(true)
  expect((await request.post(`/api/workspaces/${workspaceId}/tags/apply`, { data: { tag: 'DeckTag', paper_ids: [paperId] } })).ok()).toBe(true)

  await page.goto(`/#/workspaces/${workspaceId}?tags=DeckTag`)
  await expect(rowOf(page, paperId)).toBeVisible()
  await expect(rowOf(page, secondPaperId)).toHaveCount(0)

  await viewSwitch(page).getByRole('button', { name: 'Deck' }).click()
  await expect(deck(page)).toBeVisible()
  await expect(status(page)).toContainText('paper 1 of 1')
  await expect(page.getByRole('button', { name: 'Paper actions' })).toHaveCount(0)

  await viewSwitch(page).getByRole('button', { name: 'List' }).click()
  await expect(rowOf(page, paperId)).toBeVisible()
  await expect(rowOf(page, secondPaperId)).toHaveCount(0)
})
