import { addTable, expect, openReader, test } from './fixtures'

// The fixture's page 2 starts below the fold at the reader's zoom, so being in view proves the reader scrolled there.

test("the Data tab lists a paper's tables, and Show in paper flashes the table on its page", async ({
  page,
  request,
  paperId,
}) => {
  await openReader(page, paperId)
  await page.getByRole('tab', { name: 'Data' }).click()
  await expect(page.getByText('No data from this paper yet.')).toBeVisible()

  const table = await addTable(request, paperId, 2, 'Table 1: Results on the dev set.', [
    ['System', 'F1'],
    ['BERT-B', '88.5'],
    ['BERT-L', '90.9'],
  ])
  await page.reload()
  const card = page.locator(`article.dataset-card[data-dataset-id="${table.id}"]`)
  await expect(card).toContainText('Table 1: Results on the dev set.')
  await expect(card).toContainText('p. 2 · 2 rows × 2 columns')

  await card.getByRole('button', { name: 'Show in paper' }).click()
  const flash = page.locator('.pdf-page[data-page="2"] .chunk-flash')
  await expect(flash).toHaveCount(1)
  await expect(flash).toBeInViewport()
})

test('a region link opens the Data tab and flashes that place once, then leaves the hash', async ({ page, paperId }) => {
  await page.goto(`/#/papers/${paperId}?tab=data&page=2&rects=72,110,300,124;72,126,300,140`)

  const flash = page.locator('.pdf-page[data-page="2"] .chunk-flash')
  await expect(flash.first()).toBeInViewport()
  await expect(flash).toHaveCount(2)
  await expect(page.getByRole('tab', { name: 'Data' })).toHaveAttribute('aria-selected', 'true')
  await expect(page).toHaveURL(new RegExp(`#/papers/${paperId}\\?tab=data$`))
})
