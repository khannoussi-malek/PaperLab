import { expect, test } from './fixtures'

test('the search model is ready, the embedding model is locked once papers are indexed, and re-indexing asks first', async ({
  page,
  paperId,
}) => {
  expect(paperId).toBeTruthy() // an ingested paper, so the library has chunks
  let reindexCalls = 0
  // Re-indexing the owner's whole library is never run for real here: the request is answered by the test.
  await page.route('**/api/embedding/reindex', (route) => {
    reindexCalls += 1
    return route.fulfill({ status: 202, json: { papers: 3 } })
  })
  await page.goto('/#/settings/search')

  const section = page.getByRole('region', { name: 'Search' })
  // This stack has the search model (it was downloaded into the models volume); the no-model view is no-search-model.spec.ts.
  await expect(section.locator('.search-model-status')).toHaveText('Search model: ready')
  await expect(section.getByRole('button', { name: /^Download search model/ })).toHaveCount(0)
  await expect(section.getByRole('combobox', { name: 'Embedding model' })).toBeDisabled()
  // One model, or several while a library waits for a re-index (int8 vectors beside older ones).
  await expect(section.locator('.embedding-indexed')).toHaveText(/^indexed with \S+(, \S+)* · [\d,]+ chunks?$/)

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

test('a failed re-index shows the server error and leaves the dialog open to retry or cancel', async ({ page }) => {
  // Re-indexing the owner's whole library is never run for real here: the request is answered by the test.
  await page.route('**/api/embedding/reindex', (route) => route.fulfill({ status: 500, json: { detail: 'Re-index failed' } }))
  await page.goto('/#/settings/search')

  const section = page.getByRole('region', { name: 'Search' })
  await section.getByRole('button', { name: 'Re-index library' }).click()
  const confirm = page.getByRole('dialog', { name: 'Re-index the library?' })
  await confirm.getByRole('button', { name: 'Re-index' }).click()
  await expect(confirm.getByRole('alert')).toContainText('Re-index failed')
  await expect(confirm).toBeVisible()

  await confirm.getByRole('button', { name: 'Cancel' }).click()
  await expect(confirm).toBeHidden()
})
