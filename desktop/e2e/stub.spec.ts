import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test'

// The desktop app against a stub docker: no Docker, no network. Each test has its own data folder whose settings.json
// names a port nothing listens on, so a PaperLab running on :5190 is never touched.
const STUB = resolve('e2e/stub-docker.sh')
const QUIET_PORT = 5199

type Launched = { app: ElectronApplication; page: Page; calls: string }

const processEnv = () =>
  Object.fromEntries(Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined))

async function launchApp(env: Record<string, string>): Promise<Launched> {
  const dataDir = mkdtempSync(join(tmpdir(), 'paperlab-desktop-'))
  writeFileSync(join(dataDir, 'settings.json'), JSON.stringify({ port: QUIET_PORT }))
  const calls = join(dataDir, 'docker-calls.log')
  const app = await electron.launch({
    args: ['.'],
    // No docker on PATH and no fixed places, unless a test names the stub.
    env: { ...processEnv(), PATH: '/usr/bin:/bin', PAPERLAB_DATA_DIR: dataDir, PAPERLAB_DOCKER_PATHS: '', STUB_LOG: calls, ...env },
  })
  return { app, page: await app.firstWindow(), calls }
}

const title = (page: Page, name: string) => page.getByRole('heading', { level: 1, name })

function serve(html: string): Promise<{ url: string; server: Server }> {
  const server = createServer((_request, response) => response.end(html))
  return new Promise((ready) =>
    server.listen(0, '127.0.0.1', () => ready({ url: `http://127.0.0.1:${(server.address() as AddressInfo).port}/`, server })),
  )
}

test('with no docker anywhere, it says Docker is needed, with a link and Retry', async () => {
  const { app, page } = await launchApp({})
  try {
    await expect(title(page, 'Docker needed')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Get Docker Desktop' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Retry' })).toBeVisible()
  } finally {
    await app.close()
  }
})

test('a docker found only in the fixed places, not running: Start Docker, and Docker Desktop is left alone', async () => {
  const { app, page, calls } = await launchApp({ PAPERLAB_DOCKER_PATHS: STUB, STUB_INFO: 'down' })
  try {
    await expect(title(page, 'Start Docker')).toBeVisible()
    expect(readFileSync(calls, 'utf8')).toContain('info --format {{.OSType}}')
  } finally {
    await app.close()
  }
})

test('Compose older than 2.24: Update Docker', async () => {
  const { app, page } = await launchApp({ PAPERLAB_DOCKER: STUB, STUB_COMPOSE_VERSION: '2.23.3' })
  try {
    await expect(title(page, 'Update Docker')).toBeVisible()
  } finally {
    await app.close()
  }
})

test("compose up failing: Didn't start, with its last line", async () => {
  const { app, page } = await launchApp({ PAPERLAB_DOCKER: STUB, STUB_UP_ERROR: 'Error response from daemon: the stub refused' })
  try {
    await expect(title(page, "Didn't start")).toBeVisible()
    await expect(page.locator('#detail')).toHaveText('Error response from daemon: the stub refused')
  } finally {
    await app.close()
  }
})

test('closing the window stops PaperLab first, and only then exits', async () => {
  const { app, page, calls } = await launchApp({ PAPERLAB_DOCKER: STUB, STUB_STOP_SECONDS: '2' })
  try {
    await expect(title(page, 'Starting PaperLab')).toBeVisible() // up ran; nothing answers on the quiet port
    const exited = new Promise((done) => app.process().once('exit', done))

    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].close())
    await exited

    const log = readFileSync(calls, 'utf8')
    expect(log).toMatch(/ stop\n/)
    expect(log).toContain('\nstopped\n') // compose stop had finished before the app exited
  } finally {
    await app.close().catch(() => undefined) // already exited on the happy path; still safe to call again
  }
})

test('a link to another site opens in the system browser, and the window stays on PaperLab', async () => {
  const elsewhere = await serve('<!doctype html><title>Elsewhere</title>')
  const paperlab = await serve(`<!doctype html><title>PaperLab</title><a id="out" href="${elsewhere.url}">elsewhere</a>`)
  const { app, page } = await launchApp({ PAPERLAB_URL: paperlab.url })
  try {
    await app.evaluate(({ shell }) => {
      const opened: string[] = []
      Object.assign(globalThis, { opened })
      Object.assign(shell, { openExternal: async (url: string) => void opened.push(url) })
    })
    await expect(page).toHaveURL(paperlab.url)

    await page.click('#out', { noWaitAfter: true }) // will-navigate cancels this navigation; Playwright would wait for its end forever

    await expect.poll(() => app.evaluate(() => (globalThis as unknown as { opened: string[] }).opened)).toEqual([elsewhere.url])
    expect(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.getURL())).toBe(paperlab.url) // the main process's URL: page.url waits on that cancelled navigation
  } finally {
    await app.close()
    elsewhere.server.close()
    paperlab.server.close()
  }
})
