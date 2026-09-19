import { fileURLToPath } from 'node:url'
import type { APIRequestContext, Locator, Page } from '@playwright/test'
import { addNote, test as base, expect, removePaperAndNotes, uploadAndWaitUntilReady } from './fixtures'
import { FREE_SOURCES_ON, MOVES_PAPER_SOURCES, readSourceSettings, setSourceSettings, type SourceSettings } from './paperSources'

// citation-paper.pdf (fixtures/make_citation_paper.py): page 1 cites [1]–[4], each number linked to its entry in page
// 2's two-column reference list; "Figure 1" and "2 pages" are links that are not citations; a plain [5] has no link.
const CITATION_FIXTURE_FILE = fileURLToPath(new URL('./fixtures/citation-paper.pdf', import.meta.url))
const FIRST_BODY_LINE = 'Fixtures cite fixtures'
// Points on page 1, in PDF points (the generator's own layout, measured with PyMuPDF's search_for).
const FIGURE_1: Point = [92, 148]
const TWO_PAGES: Point = [159, 164]
const PLAIN_5: Point = [289, 148]
/** Inside `addNote`'s highlight on the first body line ([72, 110, 540, 124]), clear of every citation. */
const IN_HIGHLIGHT: Point = [100, 116]
// The fake discovery provider's three references (backend/app/providers/discovery_fake.py), as in references.spec.ts.
const FREE = 'PaperLab Find Papers Fixture'
const CLOSED = 'PaperLab Closed Access Fixture'
const FAKE_DOI_PREFIX = '10.5555/paperlab-e2e-'

type Point = [number, number]

const test = base.extend<{ citationPaperId: string }>({
  /** A freshly ingested copy of the citation fixture, removed after the test even if it fails. */
  citationPaperId: async ({ request }, use) => {
    const id = await uploadAndWaitUntilReady(request, CITATION_FIXTURE_FILE, 'citation-paper.pdf')
    await use(id)
    await removePaperAndNotes(request, id)
  },
})

/** Opens the fixture and waits for its four citation buttons: the idle-time pass has run. */
async function openCitationPaper(page: Page, paperId: string) {
  await page.goto(`/#/papers/${paperId}`)
  await expect(page.locator('.pdf-page[data-page="1"] .textLayer span', { hasText: FIRST_BODY_LINE })).toBeVisible()
  await expect(page.locator('.pdf-page[data-page="1"] .citation-link')).toHaveCount(4)
}

/** Moves the mouse like a person (MASTER's Motion rule): many small steps, then a rest. */
async function glide(page: Page, x: number, y: number) {
  await page.mouse.move(x, y, { steps: 25 })
  await page.mouse.move(x + 1, y)
  await page.waitForTimeout(150)
}

/** Glides to a point given in PDF points on a page, at whatever zoom the reader shows. */
async function glideToPoint(page: Page, pageNumber: number, [x, y]: Point) {
  const box = (await page.locator(`.pdf-page[data-page="${pageNumber}"]`).boundingBox())!
  const scale = box.width / 612 // US Letter
  await glide(page, box.x + x * scale, box.y + y * scale)
}

const citationButton = (page: Page, label: number) =>
  page.getByRole('button', { name: `Reference ${label}`, exact: true })

/** Glides to a citation's centre: its button sits exactly over its link. */
async function glideToCitation(page: Page, label: number) {
  const box = (await citationButton(page, label).boundingBox())!
  await glide(page, box.x + box.width / 2 - 1, box.y + box.height / 2)
}

async function clickCitation(page: Page, label: number) {
  const box = (await citationButton(page, label).boundingBox())!
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
}

/** Whether `inner`'s centre lies inside `outer`. */
async function covers(outer: Locator, inner: Locator): Promise<boolean> {
  const [a, b] = [await outer.boundingBox(), await inner.boundingBox()]
  if (!a || !b) return false
  const [x, y] = [b.x + b.width / 2, b.y + b.height / 2]
  return x >= a.x && x <= a.x + a.width && y >= a.y && y <= a.y + a.height
}

test('a linked citation shows its entry as the PDF prints it, and offers to look the references up', async ({
  page,
  citationPaperId,
}) => {
  await openCitationPaper(page, citationPaperId)
  await glideToCitation(page, 3)

  const card = page.locator('.citation-card')
  await expect(card).toHaveCount(1)
  await expect(card).toHaveAttribute('aria-label', 'Reference 3')
  await expect(card.getByText('Reference 3', { exact: true })).toBeVisible()
  await expect(card.getByText("From this paper's reference list")).toBeVisible()
  await expect(
    card.getByText('[3] Some Author. 2019. A paper this library has never stored. Unknown Venue.', { exact: true }),
  ).toBeVisible()
  await expect(card.getByText("This paper's references haven't been looked up.")).toBeVisible()
  // Not clicked here: that queues a fetch, which only the @moves-paper-sources test may do.
  await expect(card.getByRole('button', { name: 'Open References' })).toBeVisible()
})

test('only linked [N] citations get a card, one card shows at a time, and a note being edited keeps it', async ({
  page,
  request,
  citationPaperId,
}) => {
  await addNote(request, citationPaperId, 1, 'citation overlap note') // a highlight over body line 1: [1], [2] and [3]
  await openCitationPaper(page, citationPaperId)
  const citationCard = page.locator('.citation-card')
  const noteCard = page.locator('.note-hover-card')

  // A figure link, an "N pages" link and an unlinked [5]: none is a citation.
  for (const point of [FIGURE_1, TWO_PAGES, PLAIN_5]) {
    await glideToPoint(page, 1, point)
    await expect(citationCard).toHaveCount(0)
  }

  // Inside the highlight, the note's card; on [1], inside the same highlight, the citation's card instead.
  await glideToPoint(page, 1, IN_HIGHLIGHT)
  await expect(noteCard).toContainText('citation overlap note')
  await glideToCitation(page, 1)
  await expect(citationCard).toHaveAttribute('aria-label', 'Reference 1')
  await expect(noteCard).toHaveCount(0)

  // While the note is being edited, a citation never takes the card.
  await glideToPoint(page, 1, IN_HIGHLIGHT)
  const box = (await page.locator('.pdf-page[data-page="1"]').boundingBox())!
  const scale = box.width / 612
  await page.mouse.click(box.x + IN_HIGHLIGHT[0] * scale, box.y + IN_HIGHLIGHT[1] * scale, { button: 'right' })
  await page.getByRole('menuitem', { name: 'Edit note' }).click()
  await expect(noteCard.getByRole('textbox', { name: 'Edit note' })).toBeFocused()
  await glideToCitation(page, 1)
  await page.waitForTimeout(400) // past the 300 ms close delay
  await expect(noteCard.getByRole('textbox', { name: 'Edit note' })).toBeVisible()
  await expect(citationCard).toHaveCount(0)

  // Task 6's fix (22feb0f): a citation jump while the note is being edited keeps that note's card and its unsaved text.
  const editBox = noteCard.getByRole('textbox', { name: 'Edit note' })
  await editBox.fill('citation overlap note, still editing')
  await clickCitation(page, 2)
  await expect(page.locator('.pdf-page[data-page="2"] .chunk-flash').first()).toBeInViewport() // the jump happened
  await expect(editBox).toBeVisible() // stays in the DOM on page 1, even scrolled out of view
  await expect(editBox).toHaveValue('citation overlap note, still editing')
})

test('a click jumps to the entry in the reference list, and Back returns to the citation', async ({
  page,
  citationPaperId,
}) => {
  await openCitationPaper(page, citationPaperId)
  const bodyLine = page.locator('.pdf-page[data-page="1"] .textLayer span', { hasText: FIRST_BODY_LINE })

  await clickCitation(page, 2)
  // [2] opens page 2's left column at its foot: the flash is there, over the entry's first line.
  const flash = page.locator('.pdf-page[data-page="2"] .chunk-flash').first()
  await expect(flash).toBeInViewport()
  await expect(page.locator('.pdf-page[data-page="2"] .chunk-flash')).toHaveCount(4) // [2]'s four lines, both columns
  const label = page.locator('.pdf-page[data-page="2"] .textLayer span').filter({ hasText: /^\[2\]$/ })
  await expect.poll(() => covers(flash, label)).toBe(true)
  await expect(bodyLine).not.toBeInViewport()

  // Q1 (b): the way back to the citation.
  const back = page.getByRole('button', { name: 'Back to page 1' })
  await expect(back).toBeVisible()
  await back.click()
  await expect(bodyLine).toBeInViewport()
  await expect(back).toHaveCount(0)

  // Task 7's fix (fbcc6e0): the saved spot carries its scale; a zoom change hides the pill until it comes back to it.
  await clickCitation(page, 2)
  await expect(back).toBeVisible()
  await page.getByRole('button', { name: 'Zoom in' }).click()
  await expect(back).toHaveCount(0)
  await page.getByRole('button', { name: 'Zoom out' }).click()
  await expect(back).toBeVisible()
})

test('citations work from the keyboard: focus opens the card, Tab enters it, Escape closes it, Enter jumps', async ({
  page,
  citationPaperId,
}) => {
  await openCitationPaper(page, citationPaperId)
  const reference = citationButton(page, 1)

  // The first citation is the first tab stop after the toolbar.
  await page.getByRole('button', { name: 'Toggle theme' }).focus()
  await page.keyboard.press('Tab')
  await expect(reference).toBeFocused()
  const card = page.getByRole('region', { name: 'Reference 1' })
  await expect(card).toBeVisible()
  await expect(reference).toHaveAttribute('aria-expanded', 'true')

  await page.keyboard.press('Tab')
  await expect(card.getByRole('button', { name: 'Open References' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(card).toHaveCount(0)
  await expect(reference).toBeFocused()

  await page.keyboard.press('Enter')
  await expect(page.locator('.pdf-page[data-page="2"] .chunk-flash').first()).toBeInViewport()
  // Q1 (b): focus follows to the way back.
  await expect(page.getByRole('button', { name: 'Back to page 1' })).toBeFocused()
})

/** Papers the test imported from the fake's fixed DOIs would show as In library in the next run: removed by prefix. */
async function removeImportedFixtures(request: APIRequestContext) {
  const papers = await request.get('/api/papers')
  for (const paper of papers.ok() ? await papers.json() : []) {
    if (paper.doi?.startsWith(FAKE_DOI_PREFIX)) await removePaperAndNotes(request, paper.id)
  }
}

async function importedId(request: APIRequestContext, doi: string): Promise<string> {
  const papers: { id: string; doi: string | null }[] = await (await request.get('/api/papers')).json()
  return papers.find((paper) => paper.doi === doi)!.id
}

test.describe('once the references are looked up', () => {
  // References come from Semantic Scholar, which the owner may have switched off: the test turns the free sources on,
  // so it runs after the parallel specs, one at a time (playwright.config.ts), and puts the owner's settings back.
  let owners: SourceSettings

  test.beforeEach(async ({ request }) => {
    await removeImportedFixtures(request)
    owners = await readSourceSettings(request)
    await setSourceSettings(request, { enabled: FREE_SOURCES_ON })
  })

  test.afterEach(async ({ request }) => {
    await removeImportedFixtures(request)
    await setSourceSettings(request, owners)
  })

  test('cards become the cited papers, and one is added to the library and opened', { tag: MOVES_PAPER_SOURCES }, async ({
    page,
    request,
    citationPaperId,
  }) => {
    const refreshes: string[] = []
    page.on('request', (sent) => {
      if (sent.method() === 'POST' && sent.url().endsWith('/references/refresh')) refreshes.push(sent.url())
    })
    await openCitationPaper(page, citationPaperId)
    const card = page.locator('.citation-card')

    // The card never looks anything up itself (D140): it points at the References tab, which fetches on open (D78).
    await glideToCitation(page, 3)
    await card.getByRole('button', { name: 'Open References' }).click()
    await expect(page).toHaveURL(new RegExp(`#/papers/${citationPaperId}\\?tab=references$`))
    const panel = page.getByRole('complementary', { name: 'References' })
    await expect(panel.locator('.reference-row')).toHaveCount(3, { timeout: 30_000 })

    // [2]: matched by its title (read across the columns), no free PDF.
    await glideToCitation(page, 2)
    await expect(card.getByText(CLOSED, { exact: true })).toBeVisible()
    await expect(card.getByText('No free PDF', { exact: true })).toBeVisible()
    await expect(card.getByRole('link', { name: 'Open page' })).toBeVisible()
    await expect(card.getByRole('button', { name: 'Add to library' })).toHaveCount(0)
    await expect(card.getByRole('link', { name: 'Open in PaperLab' })).toHaveCount(0)

    // [4]: its "PDF" is a web page, so adding it fails, and the card says why.
    await glideToCitation(page, 4)
    await card.getByRole('button', { name: 'Add to library' }).click()
    await expect(card.getByRole('alert')).toContainText('No free PDF was found for this paper.')

    // [1]: the stored title, though the PDF prints another (matched by its DOI); added, then opened.
    await glideToCitation(page, 1)
    await expect(card.getByText(FREE, { exact: true })).toBeVisible()
    await card.getByRole('button', { name: 'Add to library' }).click()
    const open = card.getByRole('link', { name: 'Open in PaperLab' })
    await expect(open).toBeVisible({ timeout: 15_000 })
    await expect(card.getByRole('img', { name: `First page of ${FREE}` })).toBeVisible()
    const added = await importedId(request, `${FAKE_DOI_PREFIX}free`)
    await open.click()
    await expect(page).toHaveURL(new RegExp(`#/papers/${added}$`))
    expect(refreshes).toHaveLength(1)
  })
})
