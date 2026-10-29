import { randomUUID } from 'node:crypto'
import { expect, test } from './fixtures'

const CITED = (key: string) => `Highlights are the anchor for every note \\citep{${key}}.`
const CLAIM = 'We show that highlights anchor 100 percent of the notes.'
const CLAIM_B = 'We show that 42 notes kept their page.'
const NOT_CLAIM = 'The weather was pleasant that week.'
const GHOST = 'ghostkey'

// The reviewer end to end on the fake LLM: check, annotate, open the source, cite on a click, compile, go stale, dismiss, missing keys.
test('Review a manuscript: check citations, cite a claim, edit, dismiss, list missing keys', { tag: '@compile' }, async ({ page, request, workspaceId, paperId }) => {
  test.setTimeout(420_000)
  expect((await request.put(`/api/workspaces/${workspaceId}/papers/${paperId}`)).status()).toBe(204)
  let manuscriptId = ''
  const file = async () => (await (await request.get(`/api/manuscripts/${manuscriptId}/files/main.tex`)).json()) as { text: string; updated_at: string }
  const source = async () => (await file()).text
  try {
    await page.goto(`/#/workspaces/${workspaceId}?tab=write`)
    await page.getByRole('button', { name: 'New manuscript' }).click()
    await page.getByLabel('Title').fill(`E2E review ${randomUUID().slice(0, 8)}`)
    await page.getByRole('radio', { name: 'IEEE conference' }).click()
    await page.getByRole('button', { name: 'Create' }).click()
    await expect(page).toHaveURL(/#\/manuscripts\/[0-9a-f-]{36}/, { timeout: 20_000 })
    manuscriptId = /manuscripts\/([0-9a-f-]{36})/.exec(page.url())![1]

    // Fixture text: swap the abstract line for five sentences, one per line.
    const papers = (await (await request.get(`/api/manuscripts/${manuscriptId}/papers`)).json()) as { key: string }[]
    const key = papers[0].key
    const before = await file()
    const lines = [CITED(key), CLAIM, CLAIM_B, NOT_CLAIM, `Others agree \\citep{${GHOST}}.`].join('\n')
    expect(before.text).toContain('Write your abstract here.')
    const initial = before.text.replace('Write your abstract here.', lines)
    expect((await request.put(`/api/manuscripts/${manuscriptId}/files/main.tex`, { data: { text: initial, base_updated_at: before.updated_at } })).ok()).toBe(true)
    await page.reload()
    const content = page.locator('.cm-content')
    await expect(content).toContainText(CLAIM)

    // Review > Check citations, then verdicts.
    // The "Checking N of M…" line and Cancel are unit-tested (ReviewMenu.test.tsx, ReviewPanel.test.tsx): the fake model finishes too fast to assert them here.
    await page.getByRole('button', { name: 'Review' }).click()
    await page.getByRole('menuitem', { name: 'Check citations' }).click()
    const panel = page.getByRole('region', { name: 'Citation check' })
    await expect(panel).toBeVisible({ timeout: 30_000 })
    const citedRow = panel.getByRole('listitem').filter({ hasText: 'Highlights are the anchor' })
    await expect(citedRow.getByText('Supports', { exact: true })).toBeVisible({ timeout: 120_000 })
    await expect(citedRow.getByText('AI', { exact: true })).toBeVisible() // the provenance chip in the panel
    await expect(panel.getByText('Needs a citation', { exact: true })).toHaveCount(2)
    await expect(content.locator('.cm-review-badge', { hasText: /AI.*Supports/ })).toBeVisible() // and in the editor
    await expect(content.locator('.cm-review-badge', { hasText: /AI.*Needs a citation/ })).toHaveCount(2)
    await expect(panel).not.toContainText(NOT_CLAIM)

    // The quote opens the reader in a new tab.
    const popup = page.waitForEvent('popup')
    await citedRow.getByRole('link', { name: /^Page \d+$/ }).click()
    const reader = await popup
    await expect(reader).toHaveURL(/#\/papers\//)
    await reader.close()

    // Find papers > Cite this: only \citep{key} goes in, before the full stop.
    const claim = panel.getByRole('listitem').filter({ hasText: CLAIM })
    await claim.getByRole('button', { name: 'Find papers' }).click()
    await claim.getByRole('button', { name: 'Cite this' }).click()
    const cited = initial.replace(CLAIM, CLAIM.replace(/\.$/, '') + ` \\citep{${key}}.`)
    await expect.poll(source, { timeout: 30_000 }).toBe(cited)

    // Compile ok.
    await page.getByRole('button', { name: 'Compile' }).first().click()
    await expect.poll(async () => {
      try {
        return ((await (await request.get(`/api/manuscripts/${manuscriptId}`, { timeout: 30_000 })).json()) as { compile_status: string }).compile_status
      } catch (e) {
        if (e instanceof Error && /Timeout|ECONNRESET|socket hang up/.test(e.message)) return 'pending' // slow while Tectonic runs; anything else fails the test
        throw e
      }
    }, { timeout: 240_000 }).toBe('ok')

    // Edit the cited sentence: its annotation moves to "Changed since checked".
    await content.locator('.cm-line', { hasText: 'Highlights are the anchor' }).click()
    await page.keyboard.press('Home')
    await page.keyboard.type('Indeed, ')
    const changed = panel.getByRole('heading', { name: 'Changed since checked' }).locator('xpath=..')
    await expect(changed.getByRole('listitem').filter({ hasText: 'Highlights are the anchor' })).toBeVisible({ timeout: 20_000 })
    await expect(content.locator('.cm-review-badge', { hasText: /AI.*Supports/ })).toHaveCount(0)
    await expect(content.locator('.cm-review-badge', { hasText: /AI.*Needs a citation/ })).toHaveCount(1) // the other claim keeps its mark

    // Not a claim on the other claim; it stays dismissed after a reload.
    const other = panel.getByRole('listitem').filter({ hasText: CLAIM_B })
    await other.getByRole('button', { name: 'Not a claim' }).click()
    await expect(panel.getByText(/^Dismissed/)).toBeVisible()
    await page.reload()
    await expect(page.getByRole('region', { name: 'Citation check' }).getByText(/^Dismissed/)).toBeVisible({ timeout: 20_000 })

    // Cited but not found lists the ghost key with its line; clicking it jumps there.
    const missing = page.getByRole('region', { name: 'Cited but not found' })
    const ghostLine = initial.split('\n').findIndex((l) => l.includes(`\\citep{${GHOST}}`)) + 1
    const row = missing.getByRole('button', { name: new RegExp(GHOST) })
    await expect(row).toContainText(`main.tex:${ghostLine}`, { timeout: 60_000 })
    await row.click()
    await expect(page.locator('.cm-activeLine')).toContainText(`\\citep{${GHOST}}`)
    await expect(page.locator('.cm-lineNumbers .cm-activeLineGutter')).toContainText(String(ghostLine))
  } finally {
    if (manuscriptId) await request.delete(`/api/manuscripts/${manuscriptId}`)
  }
})
