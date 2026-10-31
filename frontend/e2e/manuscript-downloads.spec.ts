import { randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { expect, test } from './fixtures'

// The paper's files to take away: Download → PDF / LaTeX source (.zip) / Source and PDF (.zip), and the icon on the
// PDF itself. Before the first compile only the source can be downloaded.
test('Download the PDF, the LaTeX source, or both', { tag: '@compile' }, async ({ page, request, workspaceId }) => {
  test.setTimeout(300_000)
  const title = `E2E downloads ${randomUUID().slice(0, 8)}`
  let manuscriptId = ''
  const menu = page.getByRole('button', { name: 'Download' })
  const item = (name: string | RegExp) => page.getByRole('menuitem', { name })
  const save = async (click: () => Promise<void>) => {
    const [download] = await Promise.all([page.waitForEvent('download'), click()])
    return { name: download.suggestedFilename(), bytes: await readFile((await download.path())!) }
  }
  try {
    await page.goto(`/#/workspaces/${workspaceId}?tab=write`)
    await page.getByRole('button', { name: 'New manuscript' }).click()
    await page.getByLabel('Title').fill(title)
    await page.getByRole('radio', { name: 'Plain article' }).click()
    await page.getByRole('button', { name: 'Create' }).click()
    await expect(page).toHaveURL(/#\/manuscripts\/[0-9a-f-]{36}/, { timeout: 20_000 })
    manuscriptId = /manuscripts\/([0-9a-f-]{36})/.exec(page.url())![1]

    // Not compiled yet: PDF waits, the source is there.
    await menu.click()
    await expect(item(/^PDF/)).toHaveText('PDF — compile first')
    await expect(item(/^PDF/)).toHaveAttribute('aria-disabled', 'true')
    const latex = await save(() => item('LaTeX source (.zip)').click())
    expect(latex.name).toMatch(/-latex\.zip$|\(LaTeX\)\.zip$/)
    expect(latex.bytes.subarray(0, 2).toString()).toBe('PK')
    expect(latex.bytes.includes(Buffer.from('main.tex'))).toBe(true)
    expect(latex.bytes.includes(Buffer.from('.pdf'))).toBe(false)

    await page.getByRole('button', { name: 'Compile' }).first().click()
    const pane = page.getByRole('region', { name: 'PDF preview' })
    const paneDownload = pane.getByRole('link', { name: 'Download PDF' })
    await expect(paneDownload).toBeVisible({ timeout: 240_000 })

    const fromPane = await save(() => paneDownload.click())
    expect(fromPane.name).toBe(`${title}.pdf`)
    expect(fromPane.bytes.subarray(0, 5).toString()).toBe('%PDF-')

    await menu.click()
    const fromMenu = await save(() => item(/^PDF/).click())
    expect(fromMenu.name).toBe(`${title}.pdf`)
    expect(fromMenu.bytes.equals(fromPane.bytes)).toBe(true)

    await menu.click()
    const both = await save(() => item('Source and PDF (.zip)').click())
    expect(both.bytes.includes(Buffer.from('main.tex'))).toBe(true)
    expect(both.bytes.includes(Buffer.from('.pdf'))).toBe(true)
  } finally {
    if (manuscriptId) await request.delete(`/api/manuscripts/${manuscriptId}`)
  }
})
