import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

const TAKEN = 'A workspace with this name already exists'

const sidebar = (page: Page) => page.getByRole('navigation', { name: 'Workspaces' })

/** The sidebar row holding the workspace link named exactly `name`. */
const workspaceRow = (page: Page, name: string) =>
  sidebar(page)
    .getByRole('listitem')
    .filter({ has: page.getByRole('link', { name, exact: true }) })

async function openWorkspaceMenu(page: Page, name: string) {
  const row = workspaceRow(page, name)
  await row.hover()
  await row.getByRole('button', { name: 'Workspace actions' }).click()
}

async function workspaceIdsOf(page: Page, paperId: string): Promise<string[]> {
  const papers: { id: string; workspace_ids: string[] }[] = await (await page.request.get('/api/papers')).json()
  return papers.find((paper) => paper.id === paperId)!.workspace_ids
}

test('create a workspace, tick it on a paper, rename it, then delete it and keep the paper', async ({
  page,
  request,
  paperId,
  workspaceName,
}) => {
  await page.goto('/')
  await sidebar(page).getByRole('button', { name: 'New workspace' }).click()
  const name = sidebar(page).getByRole('textbox', { name: 'Workspace name' })
  await name.fill(workspaceName)
  await name.press('Enter')

  await expect(sidebar(page).getByRole('link', { name: workspaceName, exact: true })).toBeVisible()
  const workspaces: { id: string; name: string }[] = await (await request.get('/api/workspaces')).json()
  const workspace = workspaces.find((w) => w.name === workspaceName)!
  await expect(page).toHaveURL(new RegExp(`#/workspaces/${workspace.id}$`))

  // The paper's menu lists the workspace with a check mark that follows its membership.
  await page.goto('/')
  const row = page.locator('.paper-row').filter({ has: page.locator(`a[href="#/papers/${paperId}"]`) })
  await row.getByRole('button', { name: 'Paper actions' }).click()
  await page.getByRole('menuitem', { name: 'Add to workspace…' }).click()
  const tick = page.getByRole('menuitemcheckbox', { name: workspaceName })
  await expect(tick).toHaveAttribute('aria-checked', 'false')
  await tick.click()
  await expect(tick).toHaveAttribute('aria-checked', 'true')
  expect(await workspaceIdsOf(page, paperId)).toEqual([workspace.id])
  await page.keyboard.press('Escape')

  await openWorkspaceMenu(page, workspaceName)
  await page.getByRole('menuitem', { name: 'Rename' }).click()
  await expect(name).toHaveValue(workspaceName)
  await name.fill(`${workspaceName} renamed`)
  await name.press('Enter')
  await expect(sidebar(page).getByRole('link', { name: `${workspaceName} renamed`, exact: true })).toBeVisible()

  const confirmations: string[] = []
  page.once('dialog', (dialog) => {
    confirmations.push(dialog.message())
    void dialog.accept()
  })
  await openWorkspaceMenu(page, `${workspaceName} renamed`)
  await page.getByRole('menuitem', { name: 'Delete' }).click()
  await expect(workspaceRow(page, `${workspaceName} renamed`)).toHaveCount(0)
  expect(confirmations).toEqual([`Delete the workspace "${workspaceName} renamed"? Papers and notes stay in your library.`])
  await expect(row).toBeVisible()
  expect(await workspaceIdsOf(page, paperId)).toEqual([])
})

test('a duplicate or blank name is refused with a message, when creating and when renaming', async ({
  page,
  request,
  workspaceName,
}) => {
  for (const suffix of ['A', 'B']) {
    expect((await request.post('/api/workspaces', { data: { name: `${workspaceName} ${suffix}` } })).status()).toBe(201)
  }
  await page.goto('/')
  const name = sidebar(page).getByRole('textbox', { name: 'Workspace name' })

  await sidebar(page).getByRole('button', { name: 'New workspace' }).click()
  await name.fill(`${workspaceName} A`)
  await name.press('Enter')
  await expect(sidebar(page).getByRole('alert')).toHaveText(TAKEN)
  await name.press('Escape')
  await expect(name).toHaveCount(0)

  await openWorkspaceMenu(page, `${workspaceName} B`)
  await page.getByRole('menuitem', { name: 'Rename' }).click()
  await name.fill(`${workspaceName} A`)
  await name.press('Enter')
  await expect(sidebar(page).getByRole('alert')).toHaveText(TAKEN)
  await name.fill('   ')
  await name.press('Enter')
  await expect(sidebar(page).getByRole('alert')).toHaveText('Enter a name')

  const names = (await (await request.get('/api/workspaces')).json()).map((w: { name: string }) => w.name)
  expect(names.filter((n: string) => n.startsWith(workspaceName)).sort()).toEqual([`${workspaceName} A`, `${workspaceName} B`])
})
