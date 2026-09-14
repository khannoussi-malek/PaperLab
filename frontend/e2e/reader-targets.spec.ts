import { addNote, expect, test } from './fixtures'

// Workspace notes and citations open the reader on a target. The fixture's page 2 starts below
// the fold at the reader's 150% zoom, so being in view proves the reader scrolled there.

test('a ?note= link focuses that note on page 2, then leaves the hash', async ({ page, request, paperId }) => {
  const note = await addNote(request, paperId, 2, 'Target note')
  await page.goto(`/#/papers/${paperId}?note=${note.id}`)

  const highlight = page.locator(`.pdf-page[data-page="2"] .highlight.active[data-note-id="${note.id}"]`)
  await expect(highlight).toBeInViewport()
  await expect(page).toHaveURL(new RegExp(`#/papers/${paperId}$`))

  // One-shot: a reload opens the paper at the top with nothing focused.
  await page.reload()
  await expect(page.locator('.pdf-page[data-page="1"] .textLayer span').first()).toBeInViewport()
  await expect(page.locator('.highlight.active')).toHaveCount(0)
})

test('a ?chunk= link flashes that chunk on its page, and Back returns to where it was followed', async ({
  page,
  request,
  paperId,
}) => {
  const [chunk] = await (await request.get(`/api/papers/${paperId}/chunks?page=2`)).json()
  await page.goto('/#/')
  // exact: the library's always-on preview panel titles itself with the paper's own title, which
  // contains "PaperLab" as a substring whenever a paper is present.
  await expect(page.getByRole('heading', { name: 'PaperLab', exact: true })).toBeVisible()
  await page.evaluate(([id, chunkId]) => (window.location.hash = `#/papers/${id}?chunk=${chunkId}&page=2`), [
    paperId,
    chunk.id,
  ])

  const flash = page.locator('.pdf-page[data-page="2"] .chunk-flash')
  await expect(flash.first()).toBeInViewport()
  await expect(flash).toHaveCount(chunk.bbox.length)
  await expect(page).toHaveURL(new RegExp(`#/papers/${paperId}$`))
  await expect(flash).toHaveCount(0, { timeout: 3_000 })

  await page.goBack()
  await expect(page.getByRole('heading', { name: 'PaperLab', exact: true })).toBeVisible()
})
