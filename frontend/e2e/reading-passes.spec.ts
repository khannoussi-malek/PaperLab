import { expect, openReader, test } from './fixtures'

// Parallel-safe (D51): each test uses its own fixture paper(s), never a shared one; nothing here touches a setting.

test('sets a pass and a decision in the reader, and shows the chip after a reload', async ({ page, paperId, secondPaperId }) => {
  await openReader(page, paperId)
  const button = page.getByRole('button', { name: 'Reading' })

  await button.click()
  await page.getByRole('radio', { name: 'Pass 2' }).click()
  await expect(page.getByRole('heading', { name: 'Pass 3 · 1–5 hours' })).toBeVisible()

  await page.getByRole('radio', { name: 'Later' }).click()
  await page.keyboard.press('Escape')
  await expect(button).toBeFocused()
  await expect(button).toHaveAccessibleName('Reading Pass 2 · Later')

  await page.goto('/#/')
  await expect(page.locator(`li.paper-row[data-paper-id="${paperId}"] .reading-chip`)).toHaveText('Reading: Pass 2 · Later')
  await expect(page.locator(`li.paper-row[data-paper-id="${secondPaperId}"] .reading-chip`)).toHaveCount(0)
})

test('filters the library by reading state, and the menu sets it too', async ({ page, request, paperId, secondPaperId }) => {
  await expect(await request.put(`/api/papers/${paperId}/reading`, { data: { reading_pass: 2, triage: 'later' } })).toBeOK()
  await page.goto('/#/')

  await page.getByRole('combobox', { name: 'Reading' }).click()
  await page.getByRole('option', { name: 'Later', exact: true }).click()
  await expect(page.locator(`li.paper-row[data-paper-id="${paperId}"]`)).toBeVisible()
  await expect(page.locator(`li.paper-row[data-paper-id="${secondPaperId}"]`)).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Reading' }).click()
  await page.getByRole('option', { name: 'All papers' }).click()

  await page.locator(`li.paper-row[data-paper-id="${secondPaperId}"]`).getByRole('button', { name: 'Paper actions' }).click()
  await page.getByRole('menuitem', { name: 'Reading' }).click()
  await page.getByRole('menuitemradio', { name: 'Drop' }).click()
  await expect(page.locator(`li.paper-row[data-paper-id="${secondPaperId}"] .reading-chip`)).toHaveText('Reading: Dropped')

  await page.getByRole('combobox', { name: 'Reading' }).click()
  await page.getByRole('option', { name: 'Not read yet' }).click()
  // Q1 (b): pass 0 and not dropped. paperId is pass 2 (not unread); secondPaperId is dropped (not "unread" either).
  await expect(page.locator('li.paper-row')).toHaveCount(0)
})

test('shows the pass on the graph panel', async ({ page, request, paperId }) => {
  await expect(await request.put(`/api/papers/${paperId}/reading`, { data: { reading_pass: 2 } })).toBeOK()

  await page.goto('/#/graph')

  await expect(page.locator(`.graph-paper[data-paper-id="${paperId}"]`)).toContainText('Pass 2')
})

test('sets a pass with the keyboard, and Open References shows the References tab', async ({ page, secondPaperId }) => {
  await openReader(page, secondPaperId)
  const button = page.getByRole('button', { name: 'Reading' })

  await button.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('radio', { name: 'None yet' })).toBeFocused()
  await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('radio', { name: 'Pass 1' })).toHaveAttribute('data-state', 'checked')

  await page.getByRole('button', { name: 'Open References' }).focus()
  await page.keyboard.press('Enter')

  await expect(page.getByRole('tab', { name: 'References' })).toHaveAttribute('aria-selected', 'true')
  await expect(button).toHaveAccessibleName('Reading Pass 1')
})
