import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { expect, removePaperAndNotes, test } from './fixtures'

const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/zotero/${name}`, import.meta.url))
const TITLE_PREFIX = 'PaperLab Zotero E2E'
const ZIP_TITLE = `${TITLE_PREFIX} Zip Entry`
const PLAIN_TITLE = `${TITLE_PREFIX} Plain Entry`

test.afterEach(async ({ request }) => {
  const papers = await request.get('/api/papers')
  for (const paper of papers.ok() ? ((await papers.json()) as { id: string; title: string }[]) : []) {
    if (paper.title.startsWith(TITLE_PREFIX)) await removePaperAndNotes(request, paper.id)
  }
})

test('Zotero round trip: import a zip and a .bib, import again, then export for Zotero', async ({ page, request, workspaceId }) => {
  await page.goto(`/#/workspaces/${workspaceId}`)
  const dialog = page.getByRole('dialog', { name: 'Import from Zotero' })
  const open = async (file: string) => {
    await page.getByRole('button', { name: 'Import from Zotero' }).click()
    await dialog.getByLabel('References file').setInputFiles(fixture(file))
    await expect(dialog.getByRole('radio', { name: 'This workspace' })).toBeChecked()
    await dialog.getByRole('switch', { name: 'Fetch free PDFs for entries without one' }).click() // off: no network
  }
  const close = async () => {
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
  }

  // 1. The zip: preview, import, summary, then the paper and its note.
  await open('with-pdf.zip')
  await expect(dialog.getByText('1 reference: 0 already in your library, 1 with a PDF in the zip.')).toBeVisible()
  await dialog.getByRole('button', { name: 'Import', exact: true }).click()
  await expect(dialog.getByRole('heading', { name: 'Import finished' })).toBeVisible({ timeout: 60_000 })
  await expect(dialog.getByText(/Imported 1 new paper\. 0 were already in your library, 1 PDF attached, 1 note\./)).toBeVisible()
  await close()
  await expect(page.locator('.paper-row').filter({ hasText: ZIP_TITLE })).toBeVisible()
  // The bundled PDF is on the paper: it ingests to ready, as an uploaded PDF does.
  await expect
    .poll(
      async () => {
        const papers = (await (await request.get('/api/papers')).json()) as { title: string; status: string }[]
        return papers.find((p) => p.title === ZIP_TITLE)?.status
      },
      { timeout: 60_000 },
    )
    .toBe('ready')
  await page.getByRole('tab', { name: 'Notes' }).click()
  await expect(page.locator('a.workspace-note').filter({ hasText: 'A zip entry note from Zotero.' })).toBeVisible()
  await page.getByRole('tab', { name: 'Papers' }).click()

  // 2. A plain .bib with fetching off and saving without a PDF off: it is not imported and is listed as needing one.
  await open('one-note.bib')
  await dialog.getByRole('switch', { name: 'Save the others without a PDF' }).click() // on by default
  await expect(dialog.getByText(/1 reference has no PDF in the file and won't be imported unless fetching is on\./)).toBeVisible()
  await dialog.getByRole('button', { name: 'Import', exact: true }).click()
  await expect(dialog.getByRole('heading', { name: 'Import finished' })).toBeVisible({ timeout: 60_000 })
  await expect(dialog.getByText('Needs a PDF (1)')).toBeVisible()
  await expect(dialog.getByText(PLAIN_TITLE)).toBeVisible()
  await close()

  // 3. The zip again: deduped, nothing new.
  await open('with-pdf.zip')
  await expect(dialog.getByText(/1 reference: 1 already in your library/)).toBeVisible()
  await dialog.getByRole('button', { name: 'Import', exact: true }).click()
  await expect(dialog.getByText(/Imported 0 new papers\. 1 was already in your library, 0 PDFs attached, 0 notes\./)).toBeVisible({ timeout: 60_000 })
  await close()

  // 4. Export for Zotero: a zip with PaperLab export.bib and the PDF under files/.
  await page.getByRole('button', { name: 'Export citations' }).click()
  const download = page.waitForEvent('download')
  await page.getByRole('menuitem', { name: 'Export for Zotero (with PDFs and notes)' }).click()
  const bytes = await readFile((await (await download).path())!)
  expect(bytes.subarray(0, 2).toString('latin1')).toBe('PK')
  const names = bytes.toString('latin1') // entry names sit uncompressed in the local headers and central directory
  expect(names).toContain('PaperLab export.bib')
  expect(names).toMatch(/files\/[^/\0]+\.pdf/)

  // 5. From the library: tick the paper and export just it.
  await page.goto('/#/')
  await page.getByRole('checkbox', { name: `Select ${ZIP_TITLE}` }).check()
  await expect(page.getByRole('status').filter({ hasText: '1 selected' })).toBeVisible()
  await page.getByRole('button', { name: 'Export selected…' }).click()
  const picked = page.waitForEvent('download')
  await page.getByRole('menuitem', { name: 'BibTeX' }).click()
  const bib = (await readFile((await (await picked).path())!)).toString()
  expect(bib).toContain(ZIP_TITLE)
  expect(bib.match(/^@/gm)).toHaveLength(1) // just the ticked paper
})
