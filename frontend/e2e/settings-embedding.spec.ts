import { expect, test } from './fixtures'

test('the embedding model is locked once papers are indexed, and re-indexing asks first', async ({ page, paperId }) => {
  expect(paperId).toBeTruthy() // an ingested paper, so the library has chunks
  let reindexCalls = 0
  // Re-indexing the owner's whole library is never run for real here: the request is answered by the test.
  await page.route('**/api/embedding/reindex', (route) => {
    reindexCalls += 1
    return route.fulfill({ status: 202, json: { papers: 3 } })
  })
  await page.goto('/#/settings')

  const section = page.getByRole('region', { name: 'Embedding model' })
  await expect(section.getByRole('combobox', { name: 'Embedding model' })).toBeDisabled()
  await expect(section.locator('.embedding-indexed')).toHaveText(/^indexed with \S+ · [\d,]+ chunks?$/)

  await section.getByRole('button', { name: 'Re-index library' }).click()
  const confirm = page.getByRole('dialog', { name: 'Re-index the library?' })
  await confirm.getByRole('button', { name: 'Cancel' }).click()
  await expect(confirm).toBeHidden()
  expect(reindexCalls).toBe(0)

  await section.getByRole('button', { name: 'Re-index library' }).click()
  await confirm.getByRole('button', { name: 'Re-index' }).click()
  await expect(section.getByRole('status')).toHaveText('Re-indexing 3 papers in the background.')
  expect(reindexCalls).toBe(1)
})
