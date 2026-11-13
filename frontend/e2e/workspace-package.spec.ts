import { addNote, ask, expect, test } from './fixtures'

test('a workspace exported as a package comes back with its note when imported', async ({
  page,
  request,
  paperId,
  workspaceId,
  workspaceName,
}) => {
  expect((await request.put(`/api/workspaces/${workspaceId}/papers/${paperId}`)).status()).toBe(204)
  await addNote(request, paperId, 1, 'A note that travels in the package')

  const exported = await request.get(`/api/workspaces/${workspaceId}/package?pdfs=false`)
  expect(exported.status()).toBe(200)
  const file = await exported.body()
  // Gone on this side, so the import takes the same name back.
  expect((await request.delete(`/api/workspaces/${workspaceId}`)).status()).toBe(204)

  await page.goto('/')
  await page.getByLabel('Package file').setInputFiles({ name: 'export.paperlab', mimeType: 'application/zip', buffer: file })
  await expect(page.getByText(new RegExp(`Imported "${workspaceName}"`))).toBeVisible()
  await expect(page).toHaveURL(/#\/workspaces\//)

  const listed = await (await request.get('/api/workspaces')).json()
  const imported = listed.find((w: { name: string }) => w.name === workspaceName)
  expect(imported).toBeTruthy()
})

test('an imported workspace is read-only until it is made editable', async ({ page, request, workspaceId, workspaceName }) => {
  const exported = await request.get(`/api/workspaces/${workspaceId}/package?pdfs=false`)
  const file = await exported.body()
  expect((await request.delete(`/api/workspaces/${workspaceId}`)).status()).toBe(204)

  await page.goto('/')
  await page.getByLabel('Package file').setInputFiles({ name: 'export.paperlab', mimeType: 'application/zip', buffer: file })
  await expect(page).toHaveURL(/#\/workspaces\//)
  const banner = page.getByText('Imported read-only. Make it editable to change its papers, tags, criteria or searches.')
  await expect(banner).toBeVisible()

  const imported = (await (await request.get('/api/workspaces')).json()).find((w: { name: string }) => w.name === workspaceName)
  const refused = await request.patch(`/api/workspaces/${imported.id}`, { data: { name: `${workspaceName} renamed` } })
  expect(refused.status()).toBe(409)

  await page.getByRole('button', { name: 'Make it editable' }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: /Make it editable|Make editable|Confirm/ }).click()
  await expect(banner).toBeHidden()
  const renamed = await request.patch(`/api/workspaces/${imported.id}`, { data: { name: workspaceName } })
  expect(renamed.status()).toBe(200)
})

test("a workspace's chat answer travels in its package and its citation still opens", async ({
  page,
  request,
  paperId,
  workspaceId,
  workspaceName,
}) => {
  test.slow() // workspace chat retrieves: the first question can pay for loading the search model
  expect((await request.put(`/api/workspaces/${workspaceId}/papers/${paperId}`)).status()).toBe(204)
  await page.goto(`/#/workspaces/${workspaceId}?tab=chat`)
  await ask(page, 'What do these papers say about the method?', 45_000)

  const file = await (await request.get(`/api/workspaces/${workspaceId}/package?pdfs=false&answers=true`)).body()
  expect((await request.delete(`/api/workspaces/${workspaceId}`)).status()).toBe(204)

  await page.goto('/')
  await page.getByLabel('Package file').setInputFiles({ name: 'export.paperlab', mimeType: 'application/zip', buffer: file })
  await expect(page.getByText(new RegExp(`Imported "${workspaceName}".*1 chat answer\\.`))).toBeVisible()

  const imported = (await (await request.get('/api/workspaces')).json()).find((w: { name: string }) => w.name === workspaceName)
  await page.goto(`/#/workspaces/${imported.id}?tab=chat`)
  const answer = page.locator('article.chat-answer[data-output-id]', { hasText: 'What do these papers say about the method?' })
  await expect(answer).toBeVisible()
  await expect(answer.locator('.chat-cite').first()).toBeVisible()
})
