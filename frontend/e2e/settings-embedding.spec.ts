import { expect, test } from './fixtures'

// GET /api/embedding is answered by the test, so these never depend on the search source the owner chose, and
// re-indexing the owner's library is never run for real.
const STATUS = {
  model: 'nomic-ai/nomic-embed-text-v1.5@int8',
  chunks: 1327,
  indexed_with: [{ model: 'nomic-ai/nomic-embed-text-v1.5@int8', chunks: 1327 }],
  model_present: true,
  download_bytes: 0,
  unembedded_papers: 0,
  papers_needing_search: 0,
  source: { kind: 'builtin', connection_id: null, connection_label: null, model: null, host: null, is_local: true, label: 'Built-in' },
  rebuild: null,
  source_error: null,
  library_papers: 20,
  library_notes: 39,
  library_chars: 1_337_600,
}

test('the search model is ready, Built-in is the source, and re-indexing asks first', async ({ page }) => {
  let reindexCalls = 0
  await page.route('**/api/embedding', (route) => route.fulfill({ json: STATUS }))
  await page.route('**/api/embedding/reindex', (route) => {
    reindexCalls += 1
    return route.fulfill({ status: 202, json: { papers: 3 } })
  })
  await page.goto('/#/settings/search')

  const section = page.getByRole('region', { name: 'Search' })
  await expect(section.locator('.search-source-status')).toHaveText('Search source: Built-in')
  await expect(section.getByRole('combobox', { name: 'Search source' })).toHaveText('Built-in')
  await expect(section.locator('.search-model-status')).toHaveText('Search model: ready')
  await expect(section.getByRole('button', { name: /^Download search model/ })).toHaveCount(0)
  await expect(section.locator('.embedding-indexed')).toHaveText('indexed with nomic-ai/nomic-embed-text-v1.5@int8 · 1,327 chunks')

  await section.getByRole('button', { name: 'Re-index library' }).click()
  const confirm = page.getByRole('dialog', { name: 'Re-index the library?' })
  await expect(confirm).toContainText("Every paper's passages are embedded again with nomic-ai/nomic-embed-text-v1.5@int8, in the background.")
  await confirm.getByRole('button', { name: 'Cancel' }).click()
  await expect(confirm).toBeHidden()
  expect(reindexCalls).toBe(0)

  await section.getByRole('button', { name: 'Re-index library' }).click()
  await confirm.getByRole('button', { name: 'Re-index' }).click()
  await expect(section.getByRole('status')).toHaveText('Re-indexing 3 papers in the background.')
  expect(reindexCalls).toBe(1)
})

test('a failed re-index shows the server error and leaves the dialog open to retry or cancel', async ({ page }) => {
  await page.route('**/api/embedding', (route) => route.fulfill({ json: STATUS }))
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
