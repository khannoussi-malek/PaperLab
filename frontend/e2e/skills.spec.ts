import type { APIRequestContext, Page } from '@playwright/test'
import { ask, expect, test } from './fixtures'

// Skills are one shared list on the test stack, so these run one at a time and put every skill back afterwards:
// a default left behind would preselect a skill in every other chat spec.
test.describe.configure({ mode: 'serial' })

type Skill = { id: string; state: string; is_listed: boolean; is_paper_default: boolean; is_workspace_default: boolean }

async function restoreSkills(request: APIRequestContext) {
  const skills: Skill[] = await (await request.get('/api/skills?include_hidden=true')).json()
  for (const s of skills) {
    if (s.state === 'custom') {
      await request.delete(`/api/skills/${s.id}`)
      continue
    }
    if (s.state === 'edited') await request.post(`/api/skills/${s.id}/reset`)
    if (!s.is_listed) await request.put(`/api/skills/${s.id}`, { data: { is_listed: true } })
    if (s.is_paper_default) await request.post(`/api/skills/${s.id}/default`, { data: { scope: 'paper', on: false } })
    if (s.is_workspace_default) {
      await request.post(`/api/skills/${s.id}/default`, { data: { scope: 'workspace', on: false } })
    }
  }
}

test.beforeEach(async ({ request }) => restoreSkills(request))
test.afterEach(async ({ request }) => restoreSkills(request))

const picker = (page: Page) => page.getByRole('combobox', { name: 'Skill' })
const row = (page: Page, id: string) => page.locator(`article[data-skill-id="${id}"]`)

async function pickerOptions(page: Page): Promise<string[]> {
  await picker(page).click()
  const options = await page.getByRole('option').allTextContents()
  await page.keyboard.press('Escape')
  return options
}

async function openPaperChat(page: Page, paperId: string) {
  await page.goto(`/#/papers/${paperId}?tab=chat`)
  await expect(page.getByRole('tab', { name: 'Chat' })).toHaveAttribute('aria-selected', 'true')
}

test('a picked skill is shown on the answer it produced', async ({ page, paperId }) => {
  await openPaperChat(page, paperId)
  await picker(page).click()
  await page.getByRole('option', { name: 'Check the evaluation' }).click()
  const answer = await ask(page, 'Is the evaluation fair?')
  await expect(answer.getByText('Check the evaluation', { exact: true })).toBeVisible()  // the chip beside the AI mark
})

test('a bundled skill can be edited and reset in Settings', async ({ page }) => {
  await page.goto('/#/settings/skills')
  const evaluation = row(page, 'builtin:check-evaluation')
  await evaluation.getByRole('button', { name: 'Edit' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Instructions').fill('Only look at the baselines.')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(evaluation.getByText('Edited', { exact: true })).toBeVisible()
  await evaluation.getByRole('button', { name: 'Reset' }).click()
  await expect(evaluation.getByText('Built-in', { exact: true })).toBeVisible()
})

test('a duplicate is a custom skill, and hiding it takes it out of the picker only', async ({ page, paperId }) => {
  await page.goto('/#/settings/skills')
  await row(page, 'builtin:check-evaluation').getByRole('button', { name: 'Duplicate' }).click()
  const copy = page.locator('article[data-skill-id^="custom:"]', { hasText: 'Check the evaluation (copy)' })
  await expect(copy.getByText('Custom', { exact: true })).toBeVisible()
  await copy.getByRole('button', { name: 'Hide' }).click()
  await expect(copy.getByText('Hidden', { exact: true })).toBeVisible()

  await openPaperChat(page, paperId)
  const options = await pickerOptions(page)
  expect(options).toContain('No skill')
  expect(options).toContain('Check the evaluation')
  expect(options).not.toContain('Check the evaluation (copy)')
})

test("a paper default is preselected after a reload, and workspace chat isn't affected", async ({
  page,
  paperId,
  workspaceId,
}) => {
  await page.goto('/#/settings/skills')
  const plain = row(page, 'builtin:plain-explanation')
  await plain.getByRole('button', { name: 'Set as paper default' }).click()
  await expect(plain.getByText('Paper default', { exact: true })).toBeVisible()

  await openPaperChat(page, paperId)
  await page.reload()
  await expect(picker(page)).toContainText('Explain it plainly')

  await page.goto(`/#/workspaces/${workspaceId}?tab=chat`)
  await expect(picker(page)).toContainText('No skill')
})

test("a workspace-only skill isn't offered in the reader", async ({ page, request, paperId, workspaceId }) => {
  const created = await request.post('/api/skills', {
    data: { label: 'Compare the reading list', description: '', scope: 'workspace', instructions: 'Compare them.' },
  })
  expect(created.status()).toBe(201)

  await openPaperChat(page, paperId)
  expect(await pickerOptions(page)).not.toContain('Compare the reading list')

  await page.goto(`/#/workspaces/${workspaceId}?tab=chat`)
  expect(await pickerOptions(page)).toContain('Compare the reading list')
})
