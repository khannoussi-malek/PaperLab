import { expect, test } from './fixtures'

// Parallel-safe (D51): every assertion is scoped to this test's own workspace, so other specs' papers and the
// owner's library never change a count. Changes no settings, so no tag.
test.describe('the graph page', () => {
  test('draws the library, filters layers, focuses a paper and keeps the owner’s own link', async ({
    page,
    request,
    paperId,
    secondPaperId,
    workspaceId,
    workspaceName,
  }) => {
    for (const id of [paperId, secondPaperId]) {
      expect((await request.put(`/api/workspaces/${workspaceId}/papers/${id}`)).status()).toBe(204)
    }

    await page.goto('/')
    await page.getByRole('link', { name: 'Graph' }).click()
    await expect(page.getByRole('heading', { name: 'Graph', level: 1 })).toBeVisible()

    // Scope to this test's workspace: two papers, and the links between them only.
    await page.getByRole('combobox', { name: 'Workspace' }).click()
    await page.getByRole('option', { name: workspaceName }).click()
    const counts = page.locator('header p')
    await expect(counts).toHaveText(/^2 papers, \d+ links?/)

    // Citations and Similar content are the layers on by default (P5); unticking one lowers the count.
    const similar = page.getByRole('checkbox', { name: /^Similar content/ })
    await expect(similar).toBeChecked()
    await expect(page.getByRole('checkbox', { name: /^Same workspace/ })).not.toBeChecked()
    await similar.uncheck()
    await expect(counts).toHaveText(/^2 papers, 0 links/)
    await page.getByRole('checkbox', { name: /^Same workspace/ }).check()
    await expect(counts).toHaveText(/^2 papers, 1 link\b/)

    // Focusing a paper lists its connections; opening one lands in the reader.
    await page.locator('.graph-paper').first().click()
    const panel = page.getByRole('region', { name: 'Connected papers' })
    await expect(panel.getByRole('heading', { name: 'Same workspace' })).toBeVisible()
    const connection = panel.locator('.graph-connection a').first()
    const otherId = await connection.getAttribute('data-paper-id')
    await connection.click()
    await expect(page).toHaveURL(new RegExp(`#/papers/${otherId}$`))
    // Let the reader actually render before going back: a same-tick back() races the hash-router's remount.
    await expect(page.locator('.pdf-page[data-page="1"]').first()).toBeVisible()

    // Draw a link of the owner's own, with a label. Going back is a fresh mount of the graph page (no
    // persistence across navigation), so the workspace scope has to be picked again.
    await page.goBack()
    await page.getByRole('combobox', { name: 'Workspace' }).click()
    await page.getByRole('option', { name: workspaceName }).click()
    await page.locator('.graph-paper').first().click()
    await page.getByRole('button', { name: 'Link to another paper…' }).click()
    // Scoped to the dialog: the panel behind it also carries a `data-paper-id="${otherId}"` connection link (this
    // paper's own similar-content match), and the dialog overlay blocks a click on it anyway.
    const linkDialog = page.getByRole('dialog', { name: 'Link to another paper' })
    // The picker is a cmdk combobox, named by the hidden <label> cmdk renders from `Command label=`.
    await linkDialog.getByRole('combobox', { name: 'Paper to link to' }).fill('PaperLab E2E Fixture')
    await linkDialog.locator(`[data-paper-id="${otherId}"]`).first().click()
    // "Label" as a substring also matches the "Edit label for …" button and (once editing) the dialog's own
    // title, so the textbox needs its own role match rather than getByLabel.
    await linkDialog.getByRole('textbox', { name: 'Label' }).fill('builds on')
    await page.getByRole('button', { name: 'Save link' }).click()

    await expect(panel.getByRole('heading', { name: 'Your links' })).toBeVisible()
    await expect(panel.locator('.graph-connection', { hasText: 'builds on' })).toBeVisible()
    await expect(counts).toHaveText(/^2 papers, 2 links/)

    // The label survives an edit and a reload; removing it survives one too.
    await panel.getByRole('button', { name: /^Edit label for / }).click()
    const editDialog = page.getByRole('dialog', { name: 'Edit label' })
    await editDialog.getByRole('textbox', { name: 'Label' }).fill('contradicts')
    await page.getByRole('button', { name: 'Save link' }).click()
    await expect(panel.locator('.graph-connection', { hasText: 'contradicts' })).toBeVisible()

    await page.reload()
    await page.getByRole('combobox', { name: 'Workspace' }).click()
    await page.getByRole('option', { name: workspaceName }).click()
    // The page keeps the previous (whole-library) graph on screen while this one loads (keepPreviousData); wait
    // for the workspace's own graph to land before clicking, or the click can land on a paper outside it.
    await expect(counts).toHaveText(/^2 papers/)
    await page.getByRole('checkbox', { name: /^Your links/ }).check()
    await page.locator('.graph-paper').first().click()
    await expect(panel.locator('.graph-connection', { hasText: 'contradicts' })).toBeVisible()

    page.once('dialog', (dialog) => void dialog.accept())
    await panel.getByRole('button', { name: /^Remove link to / }).click()
    await expect(panel.getByRole('heading', { name: 'Your links' })).toBeHidden()
    await page.reload()
    await page.getByRole('combobox', { name: 'Workspace' }).click()
    await page.getByRole('option', { name: workspaceName }).click()
    await expect(counts).toHaveText(/^2 papers/)
    await page.getByRole('checkbox', { name: /^Your links/ }).check()
    await page.locator('.graph-paper').first().click()
    await expect(panel.getByRole('heading', { name: 'Your links' })).toBeHidden()
  })

  test('keeps the link dialog inside a short window when a paper has a long title', async ({
    page,
    request,
    paperId,
    secondPaperId,
    workspaceId,
    workspaceName,
  }) => {
    // Whichever paper gets focused, the other one is the only choice, so both get the long title.
    const title = `A long title ${'that keeps going '.repeat(12)}${workspaceName}`
    for (const id of [paperId, secondPaperId]) {
      expect((await request.patch(`/api/papers/${id}`, { data: { title } })).status()).toBe(200)
      expect((await request.put(`/api/workspaces/${workspaceId}/papers/${id}`)).status()).toBe(204)
    }

    await page.goto('/#/graph')
    await page.getByRole('combobox', { name: 'Workspace' }).click()
    await page.getByRole('option', { name: workspaceName }).click()
    await expect(page.locator('header p')).toHaveText(/^2 papers/)
    await page.locator('.graph-paper').first().click()
    await page.getByRole('button', { name: 'Link to another paper…' }).click()

    // The dialog fits the window (its content scrolls instead), and the long title truncates rather than
    // stretching the content past the dialog's right edge. Polled: the dialog zooms in as it opens.
    const dialog = page.getByRole('dialog', { name: 'Link to another paper' })
    await expect(dialog.getByRole('option')).toHaveCount(1)
    // One choice keeps the dialog short, so the window shrinks below it (after opening: the page itself needs room).
    await page.setViewportSize({ width: 1280, height: 300 })
    await expect
      .poll(() =>
        dialog.evaluate((element) => {
          const box = element.getBoundingClientRect()
          return { inWindow: box.top >= 0 && box.bottom <= innerHeight, spillsSideways: element.scrollWidth > element.clientWidth }
        }),
      )
      .toEqual({ inWindow: true, spillsSideways: false })
  })
})
