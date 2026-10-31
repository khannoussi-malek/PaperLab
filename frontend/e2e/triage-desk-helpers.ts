import type { APIRequestContext, Locator, Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { expect } from './fixtures'

export const desk = (page: Page): Locator => page.locator('[aria-roledescription="triage desk"]')
export const switchTo = (page: Page, name: 'List' | 'Deck' | 'Triage') =>
  page.getByRole('group', { name: 'Show papers as' }).getByRole('button', { name }).click()
export const rowOf = (page: Page, id: string) => page.locator(`li.paper-row[data-paper-id="${id}"]`)
export const pdfColumn = (page: Page) => page.locator('section[aria-label="PDF"]')

export type TriageEvent = { pile: string | null; reason: string | null; source: string; pdf_opened: boolean; pdf_ms: number | null; card_ms: number | null }

/** The id of the paper on top of the stack, from the card's own title id. */
export async function topId(page: Page): Promise<string> {
  const labelled = await page.locator('[data-triage-card]').getAttribute('aria-labelledby')
  return labelled!.replace('triage-title-', '')
}

export async function eventsOf(request: APIRequestContext, id: string): Promise<TriageEvent[]> {
  const res = await request.get(`/api/papers/${id}/triage-events`)
  expect(res.ok()).toBe(true)
  const body = await res.json()
  return Array.isArray(body) ? body : body.events
}

export async function readingOf(request: APIRequestContext, id: string) {
  const p = await (await request.get(`/api/papers/${id}`)).json()
  return { triage: p.triage as string | null, pass: (p.reading_pass ?? 0) as number }
}

/** Gives the papers one unique title, so the desk's queue holds only them while other workers' papers sit outside it. */
export async function retitle(request: APIRequestContext, ids: string[], label = 'Triagefind'): Promise<string> {
  const unique = `${label} ${randomUUID().slice(0, 8)}`
  for (const id of ids) expect((await request.patch(`/api/papers/${id}`, { data: { title: unique } })).ok()).toBe(true)
  return unique
}

/** Library, searched for `unique`, then the Triage view with the desk focused. */
export async function openDesk(page: Page, unique: string, expectedCount: number) {
  await page.goto('/#/')
  await page.getByRole('searchbox', { name: 'Search papers' }).fill(unique)
  const triage = page.getByRole('group', { name: 'Show papers as' }).getByRole('button', { name: 'Triage' })
  if ((await triage.getAttribute('aria-pressed')) !== 'true') await triage.click()
  await expect(desk(page)).toBeVisible()
  await desk(page).focus()
  await expect(page.getByText(`${expectedCount} left of ${expectedCount}`)).toBeVisible()
}

/** After a decision the next card is on top and the desk, not a button, holds focus. */
export async function decideByKey(page: Page, key: string): Promise<string> {
  const id = await topId(page)
  await page.keyboard.press(key)
  return id
}
