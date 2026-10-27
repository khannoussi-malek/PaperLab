import type { Page } from '@playwright/test'
import { addChart, addOwnData, barSpec, expect, test } from './fixtures'

const CSV = 'System,F1\nBERT-B,88.5\nBERT-L,90.9\nGPT-S,87.2\n'
const TSV = 'Model\tScore\nAlpha\t41.5\nBeta\t77.25\n'

// Real worker + Tectonic: insert a table (from a dataset, from a paste) and a chart (pgfplots, picture) at the cursor.
test('Insert tables and charts into a manuscript, compile, and keep a chart picture as figures/*.png', { tag: '@compile' }, async ({ page, request, workspaceId, dataName }) => {
  test.setTimeout(420_000)
  const dataset = await addOwnData(request, `${dataName} scores`, CSV)
  await addChart(request, `${dataName} bars`, barSpec(dataset, 'System', ['F1']))
  await addChart(request, `${dataName} boxes`, { ...barSpec(dataset, null, ['F1']), type: 'box' })
  let manuscriptId = ''
  const source = async () => (await (await request.get(`/api/manuscripts/${manuscriptId}/files/main.tex`)).json()).text as string
  const dialog = page.getByRole('dialog')
  const openInsert = async (item: 'Table…' | 'Chart…') => {
    await page.getByRole('button', { name: 'Insert' }).first().click()
    await page.getByRole('menuitem', { name: item }).click()
    await expect(dialog).toBeVisible()
  }
  const state = async () => (await (await request.get(`/api/manuscripts/${manuscriptId}`)).json()) as { compile_status: string; compiled_at: string | null }
  const compile = async (p: Page) => {
    const before = (await state()).compiled_at
    await p.getByRole('button', { name: 'Compile' }).first().click() // a click in the text would move the cursor
    await expect.poll(async () => { const s = await state(); return s.compiled_at !== before ? s.compile_status : 'pending' }, { timeout: 240_000 }).not.toBe('pending')
    const done = await (await request.get(`/api/manuscripts/${manuscriptId}`)).json()
    expect(done.compile_status, `${done.compile_friendly ?? ''}\n${(done.compile_log ?? '').slice(-1500)}\n${await source()}`).toBe('ok')
  }
  try {
    await page.goto(`/#/workspaces/${workspaceId}?tab=write`)
    await page.getByRole('button', { name: 'New manuscript' }).click()
    await page.getByLabel('Title').fill('E2E results')
    await page.getByRole('radio', { name: 'IEEE conference' }).click()
    await page.getByRole('button', { name: 'Create' }).click()
    await expect(page).toHaveURL(/#\/manuscripts\/[0-9a-f-]{36}/)
    manuscriptId = /manuscripts\/([0-9a-f-]{36})/.exec(page.url())![1]

    // Park the cursor at the end of the abstract line, as the other studio specs do.
    const editor = page.getByRole('textbox', { name: 'LaTeX source' })
    await editor.click()
    await page.keyboard.press('ControlOrMeta+Home')
    for (let i = 0; i < 12; i++) await page.keyboard.press('ArrowDown')
    await page.keyboard.press('End')

    // Table from a dataset: best = max bolds the highest F1.
    await openInsert('Table…')
    await dialog.getByRole('option', { name: new RegExp(`${dataName} scores`) }).click()
    await dialog.getByLabel('Best value').selectOption('max')
    await dialog.getByRole('tab', { name: 'LaTeX' }).click()
    await expect(dialog).toContainText('\\textbf{90.9}')
    await dialog.getByRole('button', { name: 'Insert' }).click()
    await expect(dialog).toBeHidden()
    await expect.poll(source).toContain('\\usepackage{booktabs}')
    await compile(page)
    await expect(page.getByRole('region', { name: 'PDF preview' })).toContainText('90.9', { timeout: 60_000 })

    // Table from a paste (a TSV, as Excel copies it).
    await openInsert('Table…')
    await dialog.getByRole('tab', { name: 'Paste' }).click()
    await dialog.getByLabel('Paste a table').fill(TSV)
    await dialog.getByRole('button', { name: 'Insert' }).click()
    await expect(dialog).toBeHidden()
    await expect.poll(source).toContain('77.25')

    // Bar chart as pgfplots.
    await openInsert('Chart…')
    await dialog.getByRole('option', { name: new RegExp(`${dataName} bars`) }).click()
    await dialog.getByRole('button', { name: 'Insert', exact: true }).click()
    await expect(dialog).toBeHidden()
    await expect.poll(source).toContain('\\begin{axis}')
    await compile(page)

    // Box chart: pgfplots can't draw it, so it goes in as a picture.
    await openInsert('Chart…')
    await dialog.getByRole('option', { name: new RegExp(`${dataName} boxes`) }).click()
    await expect(dialog).toContainText("pgfplots can't draw this chart type, so it goes in as a picture.")
    await dialog.getByRole('button', { name: 'Insert as a picture' }).click()
    await expect(dialog).toBeHidden({ timeout: 60_000 })
    await expect.poll(source).toContain('\\includegraphics[width=\\linewidth]{figures/')
    const detail = await (await request.get(`/api/manuscripts/${manuscriptId}`)).json()
    const png = (detail.files as { path: string }[]).find((f) => /^figures\/.+\.png$/.test(f.path))
    expect(png, 'figures/*.png is in the file list').toBeTruthy()

    // The picture is a 1950 px wide PNG with real content: decoded in the page, more than one distinct colour.
    const { width, colours } = await page.evaluate(async (url) => {
      const bitmap = await createImageBitmap(await (await fetch(url)).blob())
      const canvas = new OffscreenCanvas(bitmap.width, bitmap.height)
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(bitmap, 0, 0)
      const px = ctx.getImageData(0, 0, bitmap.width, bitmap.height).data
      const seen = new Set<number>()
      for (let i = 0; i < px.length && seen.size < 3; i += 4) seen.add((px[i] << 16) | (px[i + 1] << 8) | px[i + 2])
      return { width: bitmap.width, colours: seen.size }
    }, `/api/manuscripts/${manuscriptId}/files/${png!.path}`)
    expect(width).toBe(1950)
    expect(colours).toBeGreaterThan(1)

    await compile(page)
  } finally {
    if (manuscriptId) await request.delete(`/api/manuscripts/${manuscriptId}`)
  }
})
