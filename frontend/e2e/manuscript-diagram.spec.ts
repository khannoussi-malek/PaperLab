import { randomUUID } from 'node:crypto'
import { expect, test } from './fixtures'

// The fake LLM draws one node per double-quoted phrase, with arrows.meta and positioning.
const DESCRIPTION = 'A pipeline: "Raw data" → "Cleaning" → "Model"'
const NAMES = ['Raw data', 'Cleaning', 'Model']
const LABEL = 'fig:diagram-a-pipeline-raw-data'
const AI_COMMENT = '% diagram drawn by PaperLab AI from your description'
const PREAMBLE = ['\\usepackage{tikz}', '\\usetikzlibrary{arrows.meta}', '\\usetikzlibrary{positioning}']

const count = (text: string, part: string) => text.split(part).length - 1

// Real worker + Tectonic: draw from a description, preview, read the code, insert on a click, compile, insert again
// (a new label, no duplicate preamble), and an invalid edit that blocks Insert.
test('Draw a diagram from a description, insert it twice, compile, and block an invalid edit', { tag: '@compile' }, async ({ page, request, workspaceId }) => {
  test.setTimeout(420_000)
  let manuscriptId = ''
  const source = async () => (await (await request.get(`/api/manuscripts/${manuscriptId}/files/main.tex`)).json()).text as string
  const dialog = page.getByRole('dialog', { name: 'Draw a diagram' })
  const generate = async () => {
    await page.getByRole('button', { name: 'Insert' }).first().click()
    await page.getByRole('menuitem', { name: 'Diagram…' }).click()
    await dialog.getByLabel('Describe your diagram in a few words').fill(DESCRIPTION)
    await dialog.getByRole('button', { name: 'Generate' }).click()
    await expect(dialog.getByRole('img', { name: 'Diagram preview' }).locator('canvas')).toBeVisible({ timeout: 180_000 })
  }
  const state = async () => (await (await request.get(`/api/manuscripts/${manuscriptId}`)).json()) as { compile_status: string; compiled_at: string | null }
  try {
    await page.goto(`/#/workspaces/${workspaceId}?tab=write`)
    await page.getByRole('button', { name: 'New manuscript' }).click()
    await page.getByLabel('Title').fill(`E2E diagram ${randomUUID().slice(0, 8)}`)
    await page.getByRole('radio', { name: 'Plain article' }).click()
    await page.getByRole('button', { name: 'Create' }).click()
    await expect(page).toHaveURL(/#\/manuscripts\/[0-9a-f-]{36}/, { timeout: 20_000 })
    manuscriptId = /manuscripts\/([0-9a-f-]{36})/.exec(page.url())![1]

    // Cursor at the end of the last \input line, so the figure goes in the body.
    const content = page.locator('.cm-content')
    await content.locator('.cm-line', { hasText: '\\input{sections/conclusion}' }).click()
    await page.keyboard.press('End')

    // Generate → the preview shows → the LaTeX tab lists the three names.
    await generate()
    await dialog.getByRole('tab', { name: 'LaTeX' }).click()
    const code = dialog.getByRole('textbox', { name: 'LaTeX' })
    for (const name of NAMES) await expect(code).toHaveValue(new RegExp(name))

    // Insert: the preamble lines, the AI comment, one figure with an empty caption and a label.
    await dialog.getByRole('button', { name: 'Insert', exact: true }).click()
    await expect(dialog).toBeHidden()
    await expect.poll(source).toContain(`\\label{${LABEL}}`)
    const once = await source()
    for (const line of PREAMBLE) expect(count(once, line), line).toBe(1)
    expect(count(once, AI_COMMENT)).toBe(1)
    expect(count(once, '\\begin{figure}')).toBe(1)
    expect(once).toContain('\\caption{}')
    for (const name of NAMES) expect(once).toContain(name)

    // Compile → ok.
    const before = (await state()).compiled_at
    await page.getByRole('button', { name: 'Compile' }).first().click()
    await expect.poll(async () => { const s = await state(); return s.compiled_at !== before ? s.compile_status : 'pending' }, { timeout: 240_000 }).not.toBe('pending')
    const done = await (await request.get(`/api/manuscripts/${manuscriptId}`)).json()
    expect(done.compile_status, `${done.compile_friendly ?? ''}\n${(done.compile_log ?? '').slice(-1500)}\n${await source()}`).toBe('ok')

    // The same diagram again: the label ends -2 and the preamble gains no duplicate lines.
    await generate()
    await dialog.getByRole('button', { name: 'Insert', exact: true }).click()
    await expect(dialog).toBeHidden()
    await expect.poll(source).toContain(`\\label{${LABEL}-2}`)
    const twice = await source()
    for (const line of PREAMBLE) expect(count(twice, line), line).toBe(1)
    expect(count(twice, '\\begin{figure}')).toBe(2)

    // An invalid edit in the dialog: errors show and Insert is disabled.
    await generate()
    await dialog.getByRole('tab', { name: 'LaTeX' }).click()
    await code.fill('not a diagram')
    await dialog.getByRole('button', { name: 'Update preview' }).click()
    await expect(dialog.getByRole('listitem').filter({ hasText: 'exactly one tikzpicture' })).toBeVisible({ timeout: 60_000 })
    await expect(dialog.getByRole('button', { name: 'Insert', exact: true })).toBeDisabled()
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(dialog).toBeHidden()
    expect(await source()).toBe(twice)
  } finally {
    if (manuscriptId) await request.delete(`/api/manuscripts/${manuscriptId}`)
  }
})
