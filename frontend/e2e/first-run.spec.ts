import type { APIRequestContext, Page } from '@playwright/test'
import { addLlmConnection, expect, test } from './fixtures'

// The first-run setup (spec §5). Each test sets the one setup flag back to not done and restores it afterwards, so the
// file runs in the serial project (@moves-setup). Downloads never run: the search model's stream is answered here
// (page.route), the Ollama pull is the fake stack's, and PUT /api/llm/default is answered here so the owner's default
// never moves.

const SKIPPED = 'You can read, highlight and take notes now. Set up chat and search any time in Settings.'
const BUILT_IN_SEARCH = 'The built-in search model stays on this computer.'
const event = (name: string, data: object) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`

/** Goes to `path` and waits until the app has had GET /api/setup's answer and acted on it. */
async function openAndSettle(page: Page, path: string) {
  const answered = page.waitForResponse('**/api/setup')
  await page.goto(path)
  await answered
  await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))))
}

/** GET /api/embedding (M23's seven fields) as a fresh install sees it: the built-in model there or not as `present()`
 * says, whatever this stack has. The rest of the answer is the stack's own, read once through `request` (not
 * `route.fetch()`: the app queries this route twice in a row -- SetupSearch, then DownloadSearchModel once it mounts
 * -- and a second `route.fetch()` on the same interceptor sometimes throws "Response has been disposed"). */
async function builtInSearch(page: Page, request: APIRequestContext, present: () => boolean) {
  const real = await (await request.get('/api/embedding')).json()
  await page.route('**/api/embedding', async (route) => {
    await route.fulfill({ json: { ...real, model_present: present(), download_bytes: present() ? 0 : 548_021_671 } })
  })
}

test.describe('first-run setup @moves-setup', () => {
  test.beforeEach(async ({ request }) => {
    expect((await request.put('/api/setup', { data: { done: false } })).status()).toBe(200)
  })

  test.afterEach(async ({ request }) => {
    expect((await request.put('/api/setup', { data: { done: true } })).status()).toBe(200)
  })

  test('opens on start until Skip setup, then never again, in another browser too', async ({ page, browser }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/#\/setup$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Set up PaperLab' })).toBeVisible()
    await expect(page.getByText(SKIPPED)).toBeVisible()

    await page.getByRole('button', { name: 'Skip setup' }).click()

    await expect(page.getByRole('heading', { level: 1, name: 'PaperLab' })).toBeVisible()
    await openAndSettle(page, '/')
    await expect(page).not.toHaveURL(/#\/setup/)
    const other = await browser.newContext({ baseURL: test.info().project.use.baseURL })
    const second = await other.newPage()
    await openAndSettle(second, '/')
    await expect(second.getByRole('heading', { level: 1, name: 'PaperLab' })).toBeVisible()
    await expect(second).not.toHaveURL(/#\/setup/)
    await other.close()
  })

  test('Continue, then Finish, ends setup on the library', async ({ page, request }) => {
    await page.goto('/#/setup')
    await expect(page.getByRole('region', { name: 'Chat' })).toBeVisible()

    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByRole('region', { name: 'Search' })).toBeVisible()
    await page.getByRole('button', { name: 'Finish' }).click()

    await expect(page.getByRole('heading', { level: 1, name: 'PaperLab' })).toBeVisible()
    expect(await (await request.get('/api/setup')).json()).toEqual({ done: true })
  })

  test('picking Built-in shows the download and ends with search ready; Finish waits for it', async ({ page, request }) => {
    let downloaded = false
    let release = () => {}
    const held = new Promise<void>((resolve) => (release = resolve))
    await builtInSearch(page, request, () => downloaded)
    await page.route('**/api/embedding/model', async (route) => {
      await held // the download "runs" until the test lets it finish
      downloaded = true
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body:
          event('progress', { file: 'onnx/model.onnx', completed: 274_000_000, total: 548_021_671 }) +
          event('done', { papers_queued: 0 }),
      })
    })
    await page.goto('/#/setup')
    await page.getByRole('button', { name: 'Skip', exact: true }).click() // past chat
    const search = page.getByRole('region', { name: 'Search' })
    const status = search.locator('.search-model-status')
    await expect(status).toHaveText('Search model: not downloaded')
    await expect(search.getByText(BUILT_IN_SEARCH)).toBeVisible()

    await search.getByRole('button', { name: 'Download search model · 548 MB' }).click()
    await expect(status).toHaveText('Search model: downloading… 0%')
    await expect(search.getByRole('progressbar', { name: 'Downloading the search model' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Finish' })).toBeDisabled()
    release()

    await expect(status).toHaveText('Search model: ready')
    await expect(page.getByRole('button', { name: 'Finish' })).toBeEnabled()
  })

  test('Skip on the search step downloads nothing and ends setup on the library', async ({ page, request }) => {
    const downloads: string[] = []
    page.on('request', (sent) => {
      if (new URL(sent.url()).pathname === '/api/embedding/model') downloads.push(sent.method())
    })
    await builtInSearch(page, request, () => false)
    await page.goto('/#/setup')
    await page.getByRole('button', { name: 'Skip', exact: true }).click() // past chat
    const search = page.getByRole('region', { name: 'Search' })
    await expect(search.getByRole('button', { name: 'Download search model · 548 MB' })).toBeVisible()

    await search.getByRole('button', { name: 'Skip', exact: true }).click()

    await expect(page.getByRole('heading', { level: 1, name: 'PaperLab' })).toBeVisible()
    expect(downloads).toEqual([]) // P7: nothing downloads until it is picked
    expect(await (await request.get('/api/setup')).json()).toEqual({ done: true })
  })

  test("an Ollama pull shows its progress, and the pulled model becomes chat's default", async ({ page, request, llmName }) => {
    const ollama = await addLlmConnection(request, llmName, 'e2e-model', { kind: 'ollama', base_url: 'http://fake-ollama.test:11434' })
    // Only this connection is listed, so the step pulls into it and never into the owner's Ollama.
    await page.route('**/api/llm/connections', async (route) => {
      if (route.request().method() !== 'GET') return route.fallback()
      const all: { id: string }[] = await (await route.fetch()).json()
      await route.fulfill({ json: all.filter((connection) => connection.id === ollama.id) })
    })
    const defaults: unknown[] = []
    await page.route('**/api/llm/default', async (route) => {
      const body = route.request().postDataJSON() as { model_id: string }
      defaults.push(body)
      await route.fulfill({ json: { id: body.model_id, name: 'qwen3:4b', is_default: true } })
    })
    await page.goto('/#/setup')
    const chat = page.getByRole('region', { name: 'Chat' })
    await expect(chat.getByRole('button', { name: 'Use fake-large' })).toBeVisible() // the fake stack's installed models

    await chat.getByRole('button', { name: 'Pull qwen3:4b · 2.5 GB' }).click()

    await expect(chat.getByRole('progressbar', { name: 'Pulling qwen3:4b' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Continue' })).toBeDisabled()
    await expect(chat.locator('.setup-chat-choice')).toHaveText('Chat uses qwen3:4b.', { timeout: 15_000 })
    const listed: { id: string; models: { id: string; name: string }[] }[] = await (await request.get('/api/llm/connections')).json()
    const pulled = listed.find((connection) => connection.id === ollama.id)?.models.find((model) => model.name === 'qwen3:4b')
    expect(defaults).toEqual([{ model_id: pulled?.id }])
    await expect(page.getByRole('button', { name: 'Continue' })).toBeEnabled()
  })
})
