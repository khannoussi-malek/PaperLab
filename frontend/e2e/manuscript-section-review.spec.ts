import { randomUUID } from 'node:crypto'
import { expect, test } from './fixtures'

const FILE = 'sections/method.tex'
const FIRST = 'Describe your methods here.'
const THANKS = 'We thank the reviewers for their time.'

// Section review on the fake LLM ("Missing: <first checklist item>", "Supported: … [S1]"): review the section under
// the cursor, jump to a sentence, go stale on an edit, and pick a role for a heading PaperLab can't place.
test('Review a section: findings with an AI badge, a sentence chip, nothing written, stale on edit, a chosen role', async ({ page, request, workspaceId }) => {
  test.setTimeout(180_000)
  let manuscriptId = ''
  // The toolbar's Review menu (the panel's toggle shares the name once a card shows).
  const reviewThisSection = async () => {
    await page.getByRole('button', { name: 'Review', exact: true }).and(page.locator('[aria-haspopup="menu"]')).click()
    await page.getByRole('menuitem', { name: 'Review this section' }).click()
  }
  const file = async () => (await (await request.get(`/api/manuscripts/${manuscriptId}/files/${FILE}`)).json()) as { text: string; updated_at: string }
  try {
    await page.goto(`/#/workspaces/${workspaceId}?tab=write`)
    await page.getByRole('button', { name: 'New manuscript' }).click()
    await page.getByLabel('Title').fill(`E2E section review ${randomUUID().slice(0, 8)}`)
    await page.getByRole('radio', { name: 'Plain article' }).click()
    await page.getByRole('button', { name: 'Create' }).click()
    await expect(page).toHaveURL(/#\/manuscripts\/[0-9a-f-]{36}/, { timeout: 20_000 })
    manuscriptId = /manuscripts\/([0-9a-f-]{36})/.exec(page.url())![1]

    // Fixture text: the template's Method section, then an Acknowledgements section PaperLab has no role for.
    const before = await file()
    expect(before.text).toContain(FIRST)
    const initial = `${before.text.trimEnd()}\n\n\\section{Acknowledgements}\n${THANKS}\n`
    expect((await request.put(`/api/manuscripts/${manuscriptId}/files/${FILE}`, { data: { text: initial, base_updated_at: before.updated_at } })).ok()).toBe(true)
    await page.goto(`/#/manuscripts/${manuscriptId}?file=${encodeURIComponent(FILE)}`)
    const content = page.locator('.cm-content')
    await expect(content).toContainText(THANKS)

    // Cursor in Method → Review → Review this section: the role reads Method.
    await content.locator('.cm-line', { hasText: FIRST }).click()
    await reviewThisSection()
    const dialog = page.getByRole('dialog', { name: 'Review this section' })
    const role = dialog.getByLabel('Review “Method” as:')
    await expect(role).toHaveValue('method')
    await expect(role.locator('option:checked')).toHaveText('Method')
    await dialog.getByRole('button', { name: 'Review', exact: true }).click()
    await expect(dialog).toBeHidden()

    // Progress, then the card. "Reviewing…" itself is unit-tested (SectionFindings.test.tsx): the fake model can finish first.
    const status = page.getByRole('status', { name: 'Section review status' })
    await expect(status).toContainText(/Reviewing “Method”…|Review of “Method” done/)
    await expect(status).toContainText('Review of “Method” done: 1 missing, 0 unsupported, 1 supported.', { timeout: 60_000 })
    const panel = page.getByRole('region', { name: 'Review' })
    const card = panel.getByRole('article', { name: 'Section review of “Method”' })
    await expect(card).toContainText('Reviewed as: Method')
    await expect(card.getByText('AI', { exact: true })).toBeVisible()
    await expect(card.getByRole('group', { name: 'Missing' }).getByRole('listitem')).toHaveCount(1)
    const supported = card.getByRole('group', { name: 'Supported' })
    await expect(supported).toContainText('the opening states its topic')

    // The sentence chip only moves the selection to that sentence.
    await supported.getByRole('button', { name: `S1 · ${FIRST}` }).click()
    await expect.poll(() => page.evaluate(() => window.getSelection()?.toString())).toBe(FIRST)
    expect((await file()).text).toBe(initial) // byte-identical: nothing was inserted

    // Edit the sentence: the card moves to "Changed since reviewed".
    await content.locator('.cm-line', { hasText: FIRST }).click()
    await page.keyboard.press('Home')
    await page.keyboard.type('Briefly, ')
    const changed = panel.getByRole('heading', { name: 'Changed since reviewed' }).locator('xpath=..')
    await expect(changed.getByRole('listitem').filter({ hasText: '“Method”' })).toBeVisible({ timeout: 20_000 })
    await expect(changed.getByRole('button', { name: 'Review again' })).toBeVisible()
    await expect(card).toBeHidden()

    // Acknowledgements: no guess, so Review stays disabled until a role is chosen; Discussion runs it.
    await content.locator('.cm-line', { hasText: THANKS }).click()
    await reviewThisSection()
    const ack = dialog.getByLabel('Review “Acknowledgements” as:')
    await expect(ack).toHaveValue('')
    await expect(dialog).toContainText("PaperLab couldn't tell what kind of section this is — choose one.")
    const review = dialog.getByRole('button', { name: 'Review', exact: true })
    await expect(review).toBeDisabled()
    await ack.selectOption('discussion')
    await expect(review).toBeEnabled()
    await review.click()
    await expect(dialog).toBeHidden()
    const ackCard = panel.getByRole('article', { name: 'Section review of “Acknowledgements”' })
    await expect(ackCard).toContainText('Reviewed as: Discussion (you chose this)', { timeout: 60_000 })
    await expect(status).toContainText('Review of “Acknowledgements” done', { timeout: 60_000 })
  } finally {
    if (manuscriptId) await request.delete(`/api/manuscripts/${manuscriptId}`)
  }
})
