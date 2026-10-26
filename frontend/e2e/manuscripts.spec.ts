import { readFile } from 'node:fs/promises'
import { expect, test } from './fixtures'

// Real worker + Tectonic: write in the Write tab, compile, see a PDF, hit a stale-save conflict, download the zip.
test('Write a manuscript, compile it, resolve a conflict and download the Overleaf zip', async ({
  page, context, request, workspaceId, paperId,
}) => {
  test.setTimeout(240_000)
  expect((await request.put(`/api/workspaces/${workspaceId}/papers/${paperId}`)).status()).toBe(204)
  const exported = await request.post('/api/citations/export', { data: { paper_ids: [paperId], format: 'bibtex', workspace_id: workspaceId } })
  const title = ((await (await request.get(`/api/papers/${paperId}`)).json()) as { title: string }).title
  const key = /@\w+\{([^,\s]+),/.exec(await exported.text())?.[1]
  expect(key, 'the fixture paper has a citation key').toBeTruthy()
  let manuscriptId = ''
  try {
    await page.goto(`/#/workspaces/${workspaceId}?tab=write`)
    await page.getByRole('button', { name: 'New manuscript' }).click()
    await page.getByLabel('Title').fill('E2E manuscript')
    await page.getByRole('radio', { name: 'IEEE conference' }).click()
    await page.getByRole('button', { name: 'Create' }).click()
    await expect(page).toHaveURL(/#\/manuscripts\/[0-9a-f-]{36}/)
    manuscriptId = /manuscripts\/([0-9a-f-]{36})/.exec(page.url())![1]

    // Cite the paper at the end of the template's abstract line (12 lines down), then save + compile.
    const editor = page.getByRole('textbox', { name: 'LaTeX source' })
    await editor.click()
    await page.keyboard.press('ControlOrMeta+Home')
    for (let i = 0; i < 12; i++) await page.keyboard.press('ArrowDown')
    await page.keyboard.press('End')
    await page.keyboard.type(` \\citep{${key}}`)
    await page.keyboard.press('ControlOrMeta+s')
    await expect(page.getByRole('region', { name: 'PDF preview' }).locator('canvas').first()).toBeVisible({ timeout: 180_000 })

    // The reference list is in the PDF's text layer: its first words match the paper's title.
    // BibTeX styles re-case titles, so compare case-insensitively.
    const firstWords = title.split(/\s+/).slice(0, 2).join(' ')
    await expect(page.getByRole('region', { name: 'PDF preview' })).toContainText(new RegExp(firstWords, 'i'), { timeout: 30_000 })

    // The PDF is drawn on canvas, so prove the reference from the compile itself: it succeeded, with no
    // "Citation ... undefined" for the key, and the PDF is a real one.
    const detail = await (await request.get(`/api/manuscripts/${manuscriptId}`)).json()
    expect(detail.compile_status).toBe('ok')
    expect(detail.compile_log ?? '').not.toContain(`Citation \`${key}' on page`)
    expect(detail.compile_log ?? '').not.toMatch(new RegExp(`Citation .${key}. undefined`))
    const pdf = await request.get(`/api/manuscripts/${manuscriptId}/pdf`)
    expect((await pdf.body()).subarray(0, 4).toString()).toBe('%PDF')

    // Another tab saves first: this tab's save is stale and shows the conflict banner.
    const other = await context.newPage()
    await other.goto(page.url())
    const otherEditor = other.getByRole('textbox', { name: 'LaTeX source' })
    await otherEditor.click()
    await other.keyboard.press('ControlOrMeta+End')
    await other.keyboard.type('% from the other tab')
    await expect.poll(async () => (await (await request.get(`/api/manuscripts/${manuscriptId}/files/main.tex`)).json()).text)
      .toContain('% from the other tab') // autosaved on the server
    await editor.click()
    await page.keyboard.press('ControlOrMeta+End')
    await page.keyboard.type('% from this tab')
    await page.keyboard.press('ControlOrMeta+s')
    await expect(page.getByRole('button', { name: 'Keep my version' })).toBeVisible()
    await page.getByRole('button', { name: 'Load theirs' }).click()
    await expect(page.getByRole('button', { name: 'Keep my version' })).toBeHidden()
    await other.close()

    // The zip holds the project, the generated bib and the latexmkrc (names sit uncompressed in the zip).
    const download = page.waitForEvent('download')
    await page.getByRole('link', { name: 'Download zip' }).click()
    const zip = await readFile((await (await download).path())!)
    for (const name of ['main.tex', 'paperlab.bib', 'latexmkrc']) expect(zip.includes(Buffer.from(name)), name).toBe(true)
  } finally {
    if (manuscriptId) await request.delete(`/api/manuscripts/${manuscriptId}`)
    const left = await request.get(`/api/workspaces/${workspaceId}/manuscripts`)
    for (const m of left.ok() ? await left.json() : []) await request.delete(`/api/manuscripts/${m.id}`)
  }
})
