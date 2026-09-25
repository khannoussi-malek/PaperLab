import type { Page } from '@playwright/test'
import { expect, pickChatModel, test } from './fixtures'

// Every search-source request is answered by the test (page.route): a real switch on this stack would re-embed the
// owner's library (spec D159). No key is ever typed. GET /api/embedding answers whatever `search.set` last gave it,
// so a test moves the status (a rebuild, its end) the way the backend would.

const OPENAI = {
  id: '00000000-0000-4000-8000-00000000a001',
  kind: 'openai_compatible',
  label: 'OpenAI',
  base_url: 'https://api.openai.com/v1',
  has_key: true,
  key_hint: 'T123',
  is_local: false,
  models: [],
}
const OLLAMA = {
  id: '00000000-0000-4000-8000-00000000a002',
  kind: 'ollama',
  label: 'Ollama',
  base_url: 'http://host.docker.internal:11434',
  has_key: false,
  key_hint: null,
  is_local: true,
  models: [],
}
const BUILT_IN = { kind: 'builtin', connection_id: null, connection_label: null, model: null, host: null, is_local: true, label: 'Built-in' }
const ON_OPENAI = {
  kind: 'openai',
  connection_id: OPENAI.id,
  connection_label: 'OpenAI',
  model: 'text-embedding-3-small',
  host: 'api.openai.com',
  is_local: false,
  label: 'OpenAI',
}
const ON_OLLAMA = {
  kind: 'ollama',
  connection_id: OLLAMA.id,
  connection_label: 'Ollama',
  model: 'nomic-embed-text',
  host: 'host.docker.internal',
  is_local: true,
  label: 'Ollama',
}
const BUILT_IN_NAME = 'nomic-ai/nomic-embed-text-v1.5@int8'
const OPENAI_NAME = 'openai/text-embedding-3-small@768'
// P3 = A: the notes go too. 5,200,000 characters reproduce the owner's example (spec D157).
const SENDS =
  'This sends the text of all 20 papers and your 39 notes (about 1.3M tokens, roughly $0.03) to OpenAI, and each new paper, note and search question from now on.'

/** GET /api/embedding for a library of 20 papers and 39 notes, 5,200,000 characters, every chunk indexed with `model`. */
function status(model: string, fields: object = {}) {
  return {
    model,
    chunks: 1327,
    indexed_with: [{ model, chunks: 1327 }],
    model_present: true,
    download_bytes: 0,
    unembedded_papers: 0,
    papers_needing_search: 0,
    source: BUILT_IN,
    rebuild: null,
    source_error: null,
    library_papers: 20,
    library_notes: 39,
    library_chars: 5_200_000,
    ...fields,
  }
}

/** Answers GET /api/embedding and GET /api/llm/connections; `set` changes what the next status says. */
async function stubSearch(page: Page, first: object) {
  let current = first
  await page.route('**/api/embedding', (route) => route.fulfill({ json: current }))
  await page.route('**/api/llm/connections', (route) =>
    route.request().method() === 'GET' ? route.fulfill({ json: [OPENAI, OLLAMA] }) : route.fallback(),
  )
  return {
    set: (next: object) => {
      current = next
    },
  }
}

const event = (name: string, data: object) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`

test('switching to a cloud source asks first with what it sends, then search pauses with its progress until it is rebuilt', async ({
  page,
  paperId,
  llmConnection,
}) => {
  test.slow()
  await pickChatModel(page, llmConnection.modelId) // before the first load: it seeds the dropdown's remembered pick
  const search = await stubSearch(page, status(BUILT_IN_NAME))
  const puts: unknown[] = []
  await page.route('**/api/embedding/source', (route) => {
    puts.push(route.request().postDataJSON())
    search.set(status(OPENAI_NAME, { source: ON_OPENAI, rebuild: { done: 3, total: 20 } }))
    return route.fulfill({ status: 202, json: { papers: 20 } })
  })
  await page.goto('/#/settings/search')
  const section = page.getByRole('region', { name: 'Search' })
  const picker = section.getByRole('combobox', { name: 'Search source' })
  const dialog = page.getByRole('dialog', { name: 'Switch search to OpenAI?' })
  async function pickOpenAI() {
    await picker.click()
    await page.getByRole('option', { name: /^OpenAI\s*Cloud$/ }).click()
    await section.getByRole('button', { name: 'Switch search to OpenAI' }).click()
  }
  await expect(section.locator('.search-source-status')).toHaveText('Search source: Built-in')

  await pickOpenAI()
  await expect(dialog).toContainText(SENDS)
  await expect(dialog).toContainText(
    "Estimated at 4 characters a token and OpenAI's published price on 18 September 2026 ($0.02 per million tokens).",
  )
  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(dialog).toBeHidden()
  expect(puts).toHaveLength(0) // Cancel sends nothing
  await expect(section.locator('.search-source-status')).toHaveText('Search source: Built-in')
  await expect(picker).toHaveText('Built-in') // back to the source in use

  await pickOpenAI()
  await dialog.getByRole('button', { name: 'Switch', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(puts).toEqual([{ kind: 'openai', connection_id: OPENAI.id, model: 'text-embedding-3-small', confirm: true }])
  const rebuilding = 'Search is being rebuilt with OpenAI: 3 of 20 papers.'
  await expect(section.locator('.search-rebuild')).toContainText(rebuilding)
  await expect(section.getByRole('progressbar', { name: 'Rebuilding search' })).toBeVisible()
  await expect(section.locator('.search-source-status')).toContainText('Search source: OpenAI · text-embedding-3-small')

  await page.goto('/#/')
  await expect(page.locator('.search-notice')).toHaveText(rebuilding)
  await page.goto('/#/graph')
  await expect(page.getByText(rebuilding)).toBeVisible()

  // A long paper's chat, as the backend answers it mid-rebuild.
  await page.route(`**/api/papers/${paperId}/chat`, (route) =>
    route.request().method() === 'POST' ? route.fulfill({ status: 409, json: { detail: 'search_rebuilding' } }) : route.fallback(),
  )
  await page.goto(`/#/papers/${paperId}?tab=chat`)
  await page.getByRole('textbox', { name: 'Question' }).fill('What does it say about retrieval?')
  await page.getByRole('textbox', { name: 'Question' }).press('Enter')
  const refused = page.locator('.chat-error')
  await expect(refused.locator('.search-rebuild')).toContainText(rebuilding)
  await expect(refused.getByRole('button', { name: 'Retry' })).toHaveCount(0)

  search.set(status(OPENAI_NAME, { source: ON_OPENAI, rebuild: { done: 20, total: 20 } }))
  await expect(refused.locator('.search-rebuild')).toContainText('Search is being rebuilt with OpenAI: 20 of 20 papers.')
  search.set(status(OPENAI_NAME, { source: ON_OPENAI }))
  await expect(refused).toContainText('Search is ready again.') // the 2 s poll saw the rebuild end
  await expect(refused.getByRole('button', { name: 'Retry' })).toBeVisible()
})

test('switching to Ollama without nomic-embed-text offers its pull, which stays out of chat, then switches', async ({ page }) => {
  const search = await stubSearch(page, status(BUILT_IN_NAME))
  const puts: unknown[] = []
  await page.route('**/api/embedding/source', (route) => {
    puts.push(route.request().postDataJSON())
    if (puts.length === 1) return route.fulfill({ status: 409, json: { detail: 'embedding_model_not_pulled' } })
    search.set(status('ollama/nomic-embed-text', { source: ON_OLLAMA, rebuild: { done: 0, total: 20 } }))
    return route.fulfill({ status: 202, json: { papers: 20 } })
  })
  const pulls: unknown[] = []
  await page.route(`**/api/llm/connections/${OLLAMA.id}/pull`, (route) => {
    pulls.push(route.request().postDataJSON())
    return route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: event('progress', { status: 'pulling', total: 100, completed: 100 }) + event('done', { model: null }),
    })
  })
  await page.goto('/#/settings/search')
  const section = page.getByRole('region', { name: 'Search' })
  await section.getByRole('combobox', { name: 'Search source' }).click()
  await page.getByRole('option', { name: 'Ollama', exact: true }).click()
  await expect(section).toContainText('Runs on host.docker.internal. Nothing leaves your network.')
  await section.getByRole('button', { name: 'Switch search to Ollama' }).click()
  const dialog = page.getByRole('dialog', { name: 'Switch search to Ollama?' })
  await expect(dialog).toContainText("Every paper's passages are embedded again with nomic-embed-text on Ollama, on this computer.")

  await dialog.getByRole('button', { name: 'Switch', exact: true }).click()
  await expect(dialog.getByRole('alert')).toHaveText("nomic-embed-text isn't in Ollama yet.")
  await dialog.getByRole('button', { name: 'Pull nomic-embed-text · 274 MB' }).click()

  await expect(dialog).toBeHidden() // the pull finished, and the second Switch went through
  expect(pulls).toEqual([{ name: 'nomic-embed-text', add_to_chat: false }])
  expect(puts).toHaveLength(2)
  await expect(section.locator('.search-rebuild')).toContainText('Search is being rebuilt with Ollama: 0 of 20 papers.')
})

test('Built-in without its model shows the download block and waits for it before switching', async ({ page }) => {
  await stubSearch(page, status(OPENAI_NAME, { source: ON_OPENAI, model_present: false, download_bytes: 138_007_688 }))
  await page.goto('/#/settings/search')
  const section = page.getByRole('region', { name: 'Search' })
  await expect(section.locator('.search-model-status')).toHaveCount(0) // another source is in use

  await section.getByRole('combobox', { name: 'Search source' }).click()
  await page.getByRole('option', { name: 'Built-in' }).click()

  await expect(section.locator('.search-model-status')).toHaveText('Search model: not downloaded')
  await expect(section.getByRole('button', { name: 'Download search model · 138 MB' })).toBeVisible()
  await expect(section.getByRole('button', { name: 'Switch search to Built-in' })).toBeDisabled()
})

test('with a cloud source, a failure offers Try again, and Re-index says what it sends again', async ({ page }) => {
  await stubSearch(page, status(OPENAI_NAME, { source: ON_OPENAI, source_error: 'Key rejected by OpenAI' }))
  const reindexes: unknown[] = []
  await page.route('**/api/embedding/reindex', (route) => {
    reindexes.push(route.request().postDataJSON())
    return route.fulfill({ status: 202, json: { papers: 2 } })
  })
  await page.goto('/#/settings/search')
  const section = page.getByRole('region', { name: 'Search' })
  await expect(section.locator('.search-source-status .cloud-tag')).toHaveText('Cloud')
  await expect(section.getByRole('alert').filter({ hasText: "Some papers couldn't be embedded" })).toContainText(
    "Some papers couldn't be embedded: Key rejected by OpenAI.",
  )

  await section.getByRole('button', { name: 'Try again' }).click()
  await expect.poll(() => reindexes).toEqual([{ confirm: true, missing_only: true }]) // resumes; never asks first

  await section.getByRole('button', { name: 'Re-index library' }).click()
  const confirm = page.getByRole('dialog', { name: 'Re-index the library?' })
  await expect(confirm).toContainText(
    'This sends the text of all 20 papers and your 39 notes (about 1.3M tokens, roughly $0.03) to OpenAI again.',
  )
  await confirm.getByRole('button', { name: 'Cancel' }).click()
  expect(reindexes).toHaveLength(1)
})

test('where search is not set up, the notice offers another search source', async ({ page }) => {
  await stubSearch(page, status(BUILT_IN_NAME, { model_present: false, download_bytes: 138_007_688, papers_needing_search: 1 }))
  await page.goto('/#/')

  const notice = page.locator('.search-notice')
  await expect(notice).toContainText("Search isn't set up: long papers and workspaces can't be searched yet.")
  await expect(notice.getByRole('link', { name: 'Use another search source' })).toHaveAttribute('href', '#/settings')
})
