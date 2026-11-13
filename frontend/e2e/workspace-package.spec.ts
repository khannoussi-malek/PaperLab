import { addNote, expect, test } from './fixtures'

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
