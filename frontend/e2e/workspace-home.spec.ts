import { FIXTURE_FILE, FIXTURE_TITLE, addNote, expect, removePaperAndNotes, test } from './fixtures'

const EMPTY = 'No papers in this workspace yet'

test('a failed load of the workspace Papers tab can be retried', async ({ page, workspaceId }) => {
  await page.route(`**/api/workspaces/${workspaceId}/papers`, (route) => route.abort(), { times: 1 })
  await page.goto(`/#/workspaces/${workspaceId}`)

  await expect(page.getByRole('alert')).toBeVisible()
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByRole('alert')).not.toBeVisible()
  await expect(page.getByText(EMPTY)).toBeVisible()
})

test('the search box on the Papers tab narrows the workspace list', async ({ page, request, paperId, workspaceId }) => {
  expect((await request.put(`/api/workspaces/${workspaceId}/papers/${paperId}`)).ok()).toBe(true)
  await page.goto(`/#/workspaces/${workspaceId}`)
  const row = page.locator(`.paper-row a[href="#/papers/${paperId}"]`)
  await expect(row).toBeVisible()

  const search = page.getByRole('searchbox', { name: 'Search papers' })
  await search.fill('no paper is called this')
  await expect(row).toHaveCount(0)
  await expect(page.getByText('No papers match “no paper is called this”')).toBeVisible()

  await search.fill('e2e fixture')
  await expect(row).toBeVisible()
})

test("add two library papers to a workspace, see both papers' notes, and open one focused in the reader", async ({
  page,
  request,
  paperId,
  secondPaperId,
  workspaceId,
  workspaceName,
}) => {
  const first = await addNote(request, paperId, 2, 'Note on the first paper')
  const second = await addNote(request, secondPaperId, 1, 'Note on the second paper')
  await page.goto(`/#/workspaces/${workspaceId}`)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(workspaceName)
  await expect(page.getByRole('tab', { name: 'Papers' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByText(EMPTY)).toBeVisible()

  await page.getByRole('button', { name: 'Add papers' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add papers' })
  await dialog.getByRole('combobox', { name: 'Search papers' }).fill(FIXTURE_TITLE)
  // Both copies share a title, and aborted runs can leave more: pick by id.
  for (const id of [paperId, secondPaperId]) {
    const option = dialog.locator(`[data-paper-id="${id}"]`)
    await option.click()
    await expect(option).toHaveAttribute('aria-checked', 'true')
  }
  await dialog.getByRole('button', { name: 'Add 2 papers' }).click()
  await expect(dialog).toHaveCount(0)

  for (const id of [paperId, secondPaperId]) {
    await expect(page.locator(`.paper-row a[href="#/papers/${id}"]`)).toBeVisible()
  }
  // Scoped to the status bar: the Chat tab's scope line repeats the counts.
  await expect(page.locator('.status-bar')).toHaveText('2 papers · 2 notes')

  await page.getByRole('tab', { name: 'Notes' }).click()
  await expect(page).toHaveURL(new RegExp(`#/workspaces/${workspaceId}\\?tab=notes$`))
  const firstNote = page.locator(`section[data-paper-id="${paperId}"] a.workspace-note[data-note-id="${first.id}"]`)
  const secondNote = page.locator(`section[data-paper-id="${secondPaperId}"] a.workspace-note[data-note-id="${second.id}"]`)
  await expect(firstNote).toContainText('Note on the first paper')
  await expect(firstNote.locator('.provenance-badge')).toHaveText('You')
  await expect(secondNote).toContainText('Note on the second paper')

  // The note is on page 2, below the fold: the reader has to scroll to it.
  await firstNote.click()
  await expect(page.locator(`.highlight.active[data-note-id="${first.id}"]`)).toBeInViewport()
  await expect(page).toHaveURL(new RegExp(`#/papers/${paperId}$`))
  await page.goBack()
  await expect(page.getByRole('tab', { name: 'Notes' })).toHaveAttribute('aria-selected', 'true')
})

test('a PDF uploaded on the Papers tab joins the workspace, and removing it from the workspace keeps it', async ({
  page,
  request,
  workspaceId,
}) => {
  await page.goto(`/#/workspaces/${workspaceId}`)
  await expect(page.getByText(EMPTY)).toBeVisible()
  const [uploaded] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/api/papers') && r.request().method() === 'POST'),
    page.locator('input[type="file"]').setInputFiles(FIXTURE_FILE),
  ])
  const { id } = await uploaded.json()

  try {
    const row = page.locator('.paper-row').filter({ has: page.locator(`a[href="#/papers/${id}"]`) })
    await expect(row.locator('.status')).toHaveText('ready', { timeout: 30_000 })
    const members = await (await request.get(`/api/workspaces/${workspaceId}/papers`)).json()
    expect(members.map((paper: { id: string }) => paper.id)).toEqual([id])

    await row.getByRole('button', { name: 'Paper actions' }).click()
    await page.getByRole('menuitem', { name: 'Remove from workspace' }).click()
    await expect(row).toHaveCount(0)
    await expect(page.getByText(EMPTY)).toBeVisible()
    expect((await request.get(`/api/papers/${id}`)).status()).toBe(200)
  } finally {
    await removePaperAndNotes(request, id)
  }
})
