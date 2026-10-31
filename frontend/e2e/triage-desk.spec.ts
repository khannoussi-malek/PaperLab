import type { Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { expect, removePaperAndNotes, test } from './fixtures'
import { decideByKey, desk, eventsOf, openDesk, pdfColumn, readingOf, retitle, rowOf, switchTo, topId } from './triage-desk-helpers'

// The triage desk on the test stack (fake providers, no LLM). Every test gives its papers one unique title and searches
// for it, so the desk's queue holds only them. Papers are removed by the fixtures; their events go with them.
const chip = (page: Page, id: string) => rowOf(page, id).locator('.reading-chip')
const wide = { width: 1440, height: 900 }
const lastEvent = async (request: Parameters<typeof eventsOf>[0], id: string) => (await eventsOf(request, id)).at(0)!

test('keys 1, 2, 3 sort three papers, the list shows each state, and U twice puts two back', async ({ page, request, paperId, secondPaperId, tablePaperId }) => {
  await page.setViewportSize(wide)
  const ids = [paperId, secondPaperId, tablePaperId]
  const unique = await retitle(request, ids)
  await openDesk(page, unique, 3)

  const first = await decideByKey(page, '1')
  await expect(desk(page)).toBeFocused()
  const second = await decideByKey(page, '2')
  const third = await decideByKey(page, '3')
  expect(new Set([first, second, third]).size).toBe(3)
  await expect(page.getByRole('heading', { name: 'That is the whole stack.' })).toBeVisible()
  await page.getByRole('button', { name: 'Show kept papers in the list' }).click()
  await expect(chip(page, first)).toHaveText('Reading: Keep')
  await expect(chip(page, second)).toHaveText('Reading: Pass 1 · Keep')
  // "Show kept" sets the Reading filter to Keep: the Later paper is not listed until All papers is chosen.
  await expect(rowOf(page, third)).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Reading' }).click()
  await page.getByRole('option', { name: 'All papers' }).click()
  await expect(chip(page, third)).toHaveText('Reading: Later')

  // A new session: include decided papers, decide two again, then U twice restores both.
  await switchTo(page, 'Triage')
  await page.getByLabel('Include decided papers').click()
  await expect(page.getByText('3 left of 3')).toBeVisible()
  await desk(page).focus()
  const a = await decideByKey(page, '4')
  await page.keyboard.press('1') // reason chip 1 commits it
  await expect(page.getByRole('group', { name: 'Reason' })).toHaveCount(0)
  const b = await decideByKey(page, '3')
  await page.keyboard.press('u')
  await page.keyboard.press('u')
  await expect(page.getByText('3 left of 3')).toBeVisible()
  for (const id of [a, b]) await expect.poll(async () => (await lastEvent(request, id)).source).toBe('undo')
  expect(await readingOf(request, first)).toEqual({ triage: 'keep', pass: 0 })
  expect(await readingOf(request, second)).toEqual({ triage: 'keep', pass: 1 })
  expect(await readingOf(request, third)).toEqual({ triage: 'later', pass: 0 })
})

test('Not relevant asks first: chips write nothing until a reason is picked; it stays in All papers and the reader keeps both changes', async ({ page, request, paperId, secondPaperId }) => {
  await page.setViewportSize(wide)
  const unique = await retitle(request, [paperId, secondPaperId])
  await openDesk(page, unique, 2)
  const id = await topId(page)
  await page.keyboard.press('4')
  await expect(page.getByRole('group', { name: 'Reason' })).toBeVisible()
  expect(await eventsOf(request, id)).toHaveLength(0)
  await page.keyboard.press('1')
  await expect.poll(async () => (await eventsOf(request, id)).map((e) => e.reason)).toEqual(['off_topic'])

  await switchTo(page, 'List')
  await expect(chip(page, id)).toHaveText('Reading: Dropped') // still in All papers, not hidden
  await page.goto(`/#/papers/${id}`)
  await page.getByRole('button', { name: 'Reading' }).click()
  await page.getByRole('radio', { name: 'Keep' }).click()
  const history = page.getByRole('region', { name: 'History' })
  await expect(history.getByRole('listitem')).toHaveCount(2)
  await expect(history).toContainText('Dropped')
  await expect(history).toContainText('from the desk')
  await expect(history).toContainText('from the reader')
})

test('the PDF column is open for a PDF paper, P hides it for good, a paper without a PDF has none, and pdf_opened follows interaction not visibility', async ({ page, request, paperId, secondPaperId, tablePaperId }) => {
  test.setTimeout(120_000)
  await page.setViewportSize(wide)
  const added = await request.post('/api/discovery/add', {
    data: { candidate: { title: 'x', doi: `10.5555/paperlab-e2e-triage-${randomUUID().slice(0, 8)}`, abstract: 'A paper saved without its PDF.' }, save_without_pdf: true },
  })
  expect(added.status()).toBe(201)
  const noPdfId = (await added.json()).id as string
  try {
    const noPdf = await retitle(request, [noPdfId], 'Triagenopdf')
    const unique = await retitle(request, [paperId, secondPaperId, tablePaperId]) // both before the list first loads
    await openDesk(page, noPdf, 1)
    await expect(page.locator('[data-triage-card]').getByText('No PDF for this paper')).toBeVisible()
    await expect(pdfColumn(page)).toHaveCount(0)

    await openDesk(page, unique, 3)
    await expect(pdfColumn(page)).toBeVisible()
    await page.keyboard.press('p')
    await expect(pdfColumn(page)).toHaveCount(0)
    await page.reload()
    await page.getByRole('searchbox', { name: 'Search papers' }).fill(unique) // the search is not remembered, nor is Triage (it reopens on the list); the PDF choice is
    await switchTo(page, 'Triage')
    await expect(page.getByText('3 left of 3')).toBeVisible()
    await expect(pdfColumn(page)).toHaveCount(0)
    await desk(page).focus()
    await page.keyboard.press('p')
    const scroller = page.getByLabel('PDF pages')
    await expect(scroller.locator('[data-page]').first()).toBeVisible()

    // 1. Decided with the column on screen and untouched: not opened.
    await page.waitForTimeout(600)
    const untouched = await decideByKey(page, '3')
    await expect.poll(async () => (await eventsOf(request, untouched)).length).toBe(1)
    expect((await lastEvent(request, untouched)).pdf_opened).toBe(false)

    // 2. A mouse-wheel scroll in the column opens it.
    await expect(scroller.locator('[data-page]').first()).toBeVisible()
    await scroller.hover()
    await page.waitForTimeout(600)
    await page.mouse.wheel(0, 250)
    await page.waitForTimeout(400)
    const scrolled = await decideByKey(page, '3')
    await expect.poll(async () => (await eventsOf(request, scrolled)).length).toBe(1)
    const e = await lastEvent(request, scrolled)
    expect(e.pdf_opened).toBe(true)
    expect(e.pdf_ms).toBeGreaterThan(0)

    // 3. The window blurs for 2.5 s: that time is not counted.
    await expect(page.locator('[data-triage-card]')).toBeVisible()
    await page.evaluate(() => window.dispatchEvent(new Event('blur')))
    await page.waitForTimeout(2500)
    const blurred = await decideByKey(page, '3')
    await expect.poll(async () => (await eventsOf(request, blurred)).length).toBe(1)
    const b = await lastEvent(request, blurred)
    expect(b.card_ms ?? 0).toBeLessThan(2000)
    expect(b.pdf_ms ?? 0).toBeLessThan(2000)
  } finally {
    await removePaperAndNotes(request, noPdfId)
  }
})

test("a workspace's Papers tab has the same desk: search narrows the queue, Include decided toggles it, the counts survive", async ({ page, request, paperId, secondPaperId, tablePaperId, workspaceId }) => {
  await page.setViewportSize(wide)
  const ids = [paperId, secondPaperId, tablePaperId]
  const unique = `Wsdesk ${randomUUID().slice(0, 8)}`
  const names = ['Alpha', 'Beta', 'Gamma']
  for (const [i, id] of ids.entries()) {
    expect((await request.patch(`/api/papers/${id}`, { data: { title: `${names[i]} ${unique}` } })).ok()).toBe(true)
    expect((await request.put(`/api/workspaces/${workspaceId}/papers/${id}`)).ok()).toBe(true)
  }
  expect((await request.put(`/api/papers/${tablePaperId}/reading`, { data: { triage: 'later' } })).ok()).toBe(true) // decided before the session
  await page.goto(`/#/workspaces/${workspaceId}`)
  await switchTo(page, 'Triage')
  const search = page.getByRole('searchbox', { name: 'Search papers' })
  const bar = page.locator('[aria-roledescription="triage desk"] > div').first()
  await expect(bar).toContainText('2 left of 2')
  await search.fill(`Alpha ${unique}`)
  await expect(bar).toContainText('1 left of 1')
  await expect(page.locator('[data-triage-card]')).toContainText('Alpha')
  await desk(page).focus()
  await page.keyboard.press('2')
  await expect(page.getByRole('heading', { name: 'That is the whole stack.' })).toBeVisible()
  await search.fill(unique)
  await expect(bar).toContainText('1 left of') // Beta: Alpha is done this session, Gamma was decided before it
  await expect(page.getByText(/^1 of \d+ decided this session/)).toBeVisible()
  await page.getByLabel('Include decided papers').click()
  await expect(bar).toContainText('2 left of')
  await expect(page.getByText(/^1 of \d+ decided this session/)).toBeVisible()
  await page.getByLabel('Include decided papers').click()
  await expect(bar).toContainText('1 left of')
})

test('a long drag decides, a short one snaps back', async ({ page, request, paperId, secondPaperId }) => {
  await page.setViewportSize(wide)
  const unique = await retitle(request, [paperId, secondPaperId])
  await openDesk(page, unique, 2)
  const drag = async (dx: number) => {
    const box = (await page.locator('[data-triage-card] h2').boundingBox())!
    const x = box.x + 20, y = box.y + box.height / 2
    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.mouse.move(x + dx / 2, y, { steps: 6 })
    await page.mouse.move(x + dx, y, { steps: 6 })
    await page.mouse.up()
  }
  const first = await topId(page)
  await drag(40)
  await page.waitForTimeout(500)
  expect(await topId(page)).toBe(first)
  expect(await eventsOf(request, first)).toHaveLength(0)
  await drag(200)
  await expect.poll(async () => (await eventsOf(request, first)).map((e) => e.pile)).toEqual(['read_closely'])
  expect(await topId(page)).not.toBe(first)
})

test('with motion on, the decided card departs as a clone that is still in flight 100 ms later (the control for the test below)', async ({ page, request, paperId, secondPaperId }) => {
  await page.setViewportSize(wide)
  const unique = await retitle(request, [paperId, secondPaperId])
  await openDesk(page, unique, 2)
  await decideByKey(page, '1')
  await page.waitForTimeout(100)
  expect(await page.locator('[data-triage-departing]').count()).toBe(1)
})

test('reduced motion: nothing departs, the same decisions, and the keys-only run keeps focus on the desk', async ({ page, request, paperId, secondPaperId, tablePaperId }) => {
  await page.setViewportSize(wide)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const unique = await retitle(request, [paperId, secondPaperId, tablePaperId])
  await openDesk(page, unique, 3)
  const d = desk(page)
  const animation = () => page.locator('[data-triage-card]').evaluate((el) => getComputedStyle(el).animationName)
  expect(await animation()).toBe('none')

  const one = await decideByKey(page, '1')
  await expect(d).toBeFocused()
  // Within ~100 ms of the key a clone would be mid-flight (it lasts 220 ms): with reduced motion none was ever made.
  await page.waitForTimeout(100)
  expect(await page.locator('[data-triage-departing]').count()).toBe(0) // a one-shot read: a retrying expect would wait the clone out
  expect(await animation()).toBe('none')
  await page.keyboard.press('4')
  await expect(page.getByRole('group', { name: 'Reason' })).toBeVisible()
  await expect(d).toBeFocused()
  await page.keyboard.press('Escape') // cancels the chips only
  await expect(page.getByRole('group', { name: 'Reason' })).toHaveCount(0)
  await expect(d).toBeFocused()
  const two = await decideByKey(page, '4')
  await page.keyboard.press('2') // wrong_method
  await expect(d).toBeFocused()
  await page.keyboard.press('u')
  await expect(d).toBeFocused()
  expect(await topId(page)).toBe(two)
  await page.keyboard.press('?')
  await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(d).toBeFocused()
  await expect.poll(async () => (await eventsOf(request, one)).map((e) => e.pile)).toEqual(['read_closely'])
  await expect.poll(async () => (await eventsOf(request, two)).map((e) => e.source)).toEqual(['undo', 'desk'])
  await page.keyboard.press('Escape') // a second Esc leaves the desk
  await expect(d).toHaveCount(0)
})

test('at 600 px: one column, no targets, five buttons by click, Open PDF opens the sheet', async ({ page, request, paperId, secondPaperId }) => {
  await page.setViewportSize({ width: 600, height: 900 })
  const unique = await retitle(request, [paperId, secondPaperId])
  await openDesk(page, unique, 2)
  await expect(desk(page)).toHaveAttribute('data-layout', 'single')
  await expect(page.locator('[data-triage-target]')).toHaveCount(0)
  const decide = page.getByRole('group', { name: 'Decide' })
  await expect(decide.getByRole('button')).toHaveCount(5)
  await page.getByRole('button', { name: 'Open PDF' }).click()
  const sheet = page.getByRole('dialog')
  await expect(sheet.locator('section[aria-label="PDF"]')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(sheet).toHaveCount(0)
  await expect(desk(page)).toBeVisible()
  const id = await topId(page)
  await decide.getByRole('button', { name: 'Skim' }).click()
  await expect.poll(async () => (await eventsOf(request, id)).map((e) => e.pile)).toEqual(['skim'])
  expect(await topId(page)).not.toBe(id)
})

test('a slow network never blocks the desk: two fast decisions, an undo at once, and the final state is right', async ({ page, request, paperId, secondPaperId, tablePaperId }) => {
  await page.setViewportSize(wide)
  const unique = await retitle(request, [paperId, secondPaperId, tablePaperId])
  await openDesk(page, unique, 3)
  await page.route('**/triage-decisions', async (route) => {
    await new Promise((r) => setTimeout(r, 1500))
    await route.continue()
  })
  const a = await decideByKey(page, '1')
  const b = await decideByKey(page, '2')
  expect(b).not.toBe(a)
  await page.keyboard.press('u')
  const started = Date.now()
  await expect(page.locator('[data-triage-card]')).toHaveAttribute('aria-labelledby', `triage-title-${b}`)
  expect(Date.now() - started).toBeLessThan(1000) // the screen answered before the server did
  await expect.poll(async () => readingOf(request, a), { timeout: 15_000 }).toEqual({ triage: 'keep', pass: 0 })
  await expect.poll(async () => readingOf(request, b), { timeout: 15_000 }).toEqual({ triage: null, pass: 0 })
  expect(await eventsOf(request, a)).toHaveLength(1) // the delayed decision was sent
  await page.unroute('**/triage-decisions')
})

test('pile keys sleep inside the PDF column; P hides it, focus returns to the desk, and the next pile key is handled', async ({ page, request, paperId, secondPaperId }) => {
  await page.setViewportSize(wide)
  const unique = await retitle(request, [paperId, secondPaperId])
  await openDesk(page, unique, 2)
  const scroller = page.getByLabel('PDF pages')
  await expect(scroller).toBeVisible()
  const id = await topId(page) // read before any key
  await scroller.focus()
  await page.keyboard.press('1') // (a) inside the column the desk's pile keys sleep
  await page.waitForTimeout(1000) // long enough for a wrongly sent decision to reach the server
  expect(await topId(page)).toBe(id)
  expect(await eventsOf(request, id)).toHaveLength(0)
  await page.keyboard.press('p') // (b) P hides the column and the desk takes focus back
  await expect(pdfColumn(page)).toHaveCount(0)
  await expect(desk(page)).toBeFocused()
  await page.keyboard.press('1')
  await expect.poll(async () => (await eventsOf(request, id)).map((e) => `${e.source}:${e.pile}`)).toEqual(['desk:read_closely'])
  expect(await topId(page)).not.toBe(id)
})
