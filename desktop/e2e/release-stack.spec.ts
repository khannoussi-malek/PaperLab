import { execFileSync, spawn, type ChildProcess } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { gunzipSync } from 'node:zlib'
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test'
import { processEnv } from './helpers'

// The desktop app over the real release stack (README, Development: E2E_RELEASE=1). This version's image is tagged
// locally, so nothing is pulled, and the library on :5190 is already migrated. Each test has its own data folder; the
// compose project is the same one.
const VERSION: string = JSON.parse(readFileSync('package.json', 'utf8')).version
const OLDER = '0.0.1' // any version below VERSION
const ELECTRON = resolve('node_modules/.bin/electron')
const FAILING_PG_DUMP = resolve('e2e/failing-pg-dump.sh')
const STARTUP = 240_000

test.describe.configure({ mode: 'serial' })

function dataFolder(settings: object = {}): string {
  const dir = mkdtempSync(join(tmpdir(), 'paperlab-release-'))
  writeFileSync(join(dir, 'settings.json'), JSON.stringify(settings))
  return dir
}

async function open(dataDir: string, env: Record<string, string> = {}): Promise<{ app: ElectronApplication; page: Page }> {
  const app = await electron.launch({ args: ['.'], env: { ...processEnv(), PAPERLAB_DATA_DIR: dataDir, ...env } })
  return { app, page: await app.firstWindow() }
}

const library = (page: Page) => page.getByRole('heading', { level: 1, name: 'PaperLab', exact: true })
const running = () =>
  execFileSync('docker', ['compose', '-p', 'paperlab-app', 'ps', '--status', 'running', '--services'], { encoding: 'utf8' })
    .split('\n')
    .filter(Boolean)
const migrateStarted = () =>
  execFileSync('docker', ['inspect', 'paperlab-app-migrate-1', '--format', '{{.State.StartedAt}}'], { encoding: 'utf8' }).trim()
const logLines = (dataDir: string) => readFileSync(join(dataDir, 'logs', 'main.log'), 'utf8').split('\n').filter(Boolean)
const isFullUp = (line: string) => / up -d → exit 0$/.test(line)
const visible = (app: ElectronApplication) => app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].isVisible())

async function closeWindow(app: ElectronApplication) {
  const exited = new Promise((done) => app.process().once('exit', done))
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].close())
  return exited
}

/** The exit code once `child` exits, or — within `ms` — rejects and kills it. A plain `child.once('exit', ...)`
 * await never settles if the process never exits (the single-instance failure the caller below exists to catch),
 * which would suspend the test forever: no assertion ever runs, and neither does its `finally`. Bounding the wait
 * turns a hang into a timely, specific failure that reaches cleanup, instead of Playwright's own generic timeout
 * reporting it with the process still running. */
function exitCode(child: ChildProcess, ms: number): Promise<number | null> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      child.kill()
      reject(new Error(`did not exit within ${ms}ms`))
    }, ms)
    child.once('exit', (code) => {
      clearTimeout(timer)
      resolve(code)
    })
  })
}

test('the window shows the library; a link elsewhere opens in the browser; Settings and Connect Claude know the app @release-stack', async () => {
  const dataDir = dataFolder()
  const { app, page } = await open(dataDir)
  try {
    await expect(library(page)).toBeVisible({ timeout: STARTUP })
    await app.evaluate(({ shell }) => {
      const opened: string[] = []
      Object.assign(globalThis, { opened })
      Object.assign(shell, { openExternal: async (url: string) => void opened.push(url) })
    })
    // Record real navigations from the main process, attached only once the initial load has settled (so that
    // transition isn't recorded too). Electron 44's will-navigate + preventDefault() cancels a navigation without
    // ever completing it (no did-fail-load, no did-navigate), so there is nothing to await for "cancelled" —
    // page.url()/toHaveURL would wait on it forever. Instead, a second, always-allowed in-app navigation (the
    // Settings hash route, below) is ordered after it: real navigations are ordered, so once that one commits, the
    // outside link's fate is already decided (stub.spec.ts's "opens in the system browser" test, same pattern).
    await app.evaluate(({ BrowserWindow }) => {
      const contents = BrowserWindow.getAllWindows()[0].webContents
      const committed: string[] = []
      Object.assign(globalThis, { committed })
      contents.on('did-navigate', (_event, url) => committed.push(url))
      contents.on('did-navigate-in-page', (_event, url) => committed.push(url))
    })

    // A string, not a closure: this file's tsconfig has no 'dom' lib (main-process code doesn't have one at
    // runtime), so `document` doesn't typecheck inside an evaluated function here either — stub.spec.ts:128 has
    // the same fix for the same reason.
    await page.evaluate(`{
      const link = Object.assign(document.createElement('a'), { href: 'http://127.0.0.1:9/elsewhere', textContent: 'elsewhere' })
      document.body.append(link)
      link.click()
    }`)
    await expect.poll(() => app.evaluate(() => (globalThis as unknown as { opened: string[] }).opened)).toEqual(['http://127.0.0.1:9/elsewhere'])

    const settingsUrl = 'http://127.0.0.1:5190/#/settings'
    await page.goto(settingsUrl) // the ordering probe: an always-allowed hash-route navigation, and the next check's own setup
    const committed = await app.evaluate(() => (globalThis as unknown as { committed: string[] }).committed)
    expect(committed).not.toContain('http://127.0.0.1:9/elsewhere') // the definitive check: the outside link's navigation never committed
    expect(committed).toContain(settingsUrl) // and the allowed one did, so the window really did reach a known state
    // The main process's own URL, as a last check: page.url() itself would wait on the cancelled navigation.
    expect(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.getURL())).toBe(settingsUrl)

    const desktop = page.getByRole('region', { name: 'Desktop app' })
    await expect(desktop.getByRole('switch', { name: 'Keep PaperLab running when the window is closed' })).toHaveAttribute('aria-checked', 'false')
    await expect(desktop.getByRole('switch', { name: 'Check for updates on launch' })).toHaveAttribute('aria-checked', 'true')

    await page.goto('http://127.0.0.1:5190/#/connect-claude')
    await expect(page.getByText('Keep the PaperLab app open (or turn on Keep running in Settings).')).toBeVisible()
    await expect(page.getByRole('textbox', { name: 'PaperLab folder' })).toHaveValue(dataDir)
  } finally {
    await app.close().catch(() => undefined) // already exited on the happy path; still safe to call again
    rmSync(dataDir, { recursive: true, force: true })
  }
})

test('with Keep running off, closing the window stops PaperLab @release-stack', async () => {
  const dataDir = dataFolder()
  const { app, page } = await open(dataDir)
  try {
    await expect(library(page)).toBeVisible({ timeout: STARTUP })

    await closeWindow(app)

    expect(running()).toEqual([])
  } finally {
    await app.close().catch(() => undefined) // already exited on the happy path; still safe to call again
    rmSync(dataDir, { recursive: true, force: true })
  }
})

test('with Keep running on, closing hides the window, a second launch shows it, and Quit stops PaperLab @release-stack', async () => {
  const dataDir = dataFolder()
  const { app, page } = await open(dataDir)
  let second: ChildProcess | undefined
  try {
    await expect(library(page)).toBeVisible({ timeout: STARTUP })
    await page.goto('http://127.0.0.1:5190/#/settings')
    const keep = page.getByRole('switch', { name: 'Keep PaperLab running when the window is closed' })
    await keep.click()
    await expect(keep).toHaveAttribute('aria-checked', 'true')

    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].close())
    await expect.poll(() => visible(app)).toBe(false)
    expect(running()).toEqual(expect.arrayContaining(['api', 'worker']))

    const secondProcess = (second = spawn(ELECTRON, ['.'], { env: { ...processEnv(), PAPERLAB_DATA_DIR: dataDir } }))
    expect(await exitCode(secondProcess, STARTUP)).toBe(0)
    await expect.poll(() => visible(app)).toBe(true)
    expect(running()).toEqual(expect.arrayContaining(['api', 'worker'])) // the second launch stopped nothing

    const exited = new Promise((done) => app.process().once('exit', done))
    await app.evaluate(({ app: electronApp }) => electronApp.quit()) // what the tray's Quit PaperLab does
    await exited
    expect(running()).toEqual([])
  } finally {
    second?.kill() // a no-op once it has already exited; catches it if it never did (the failure this test exists for)
    await app.close().catch(() => undefined) // already exited on the happy path; still safe to call again
    rmSync(dataDir, { recursive: true, force: true })
  }
})

test('an upgrade backs the library up before migrate, a restart does not, and a failed backup stops the launch @release-stack', async () => {
  const dataDir = dataFolder({ lastVersion: OLDER })
  const latest = join(dataDir, 'backups', 'latest.sql.gz')
  const temp = join(dataDir, 'backups', 'backup.sql.gz.tmp')
  let app: ElectronApplication | undefined
  let page: Page

  try {
    // One version behind: pg_dump, renamed to latest.sql.gz, then compose up (so migrate) and lastVersion.
    ;({ app, page } = await open(dataDir))
    await expect(library(page)).toBeVisible({ timeout: STARTUP })
    const first = logLines(dataDir)
    const dumped = first.findIndex((line) => line.includes(' pg_dump ') && line.endsWith('exit 0'))
    expect(dumped).toBeGreaterThan(-1)
    expect(first.findIndex(isFullUp)).toBeGreaterThan(dumped)
    expect(existsSync(temp)).toBe(false)
    expect(gunzipSync(readFileSync(latest)).toString()).toContain('CREATE TABLE public.papers')
    expect(JSON.parse(readFileSync(join(dataDir, 'settings.json'), 'utf8')).lastVersion).toBe(VERSION)
    const backedUp = createHash('sha256').update(readFileSync(latest)).digest('hex')
    await app.close()

    // The same version: no backup, compose up straight away.
    ;({ app, page } = await open(dataDir))
    await expect(library(page)).toBeVisible({ timeout: STARTUP })
    const second = logLines(dataDir).slice(first.length)
    expect(second.some((line) => line.includes('pg_dump'))).toBe(false)
    expect(second.some(isFullUp)).toBe(true)
    await app.close()

    // One version behind again, and pg_dump fails: Backup failed, latest.sql.gz untouched, migrate never runs.
    writeFileSync(join(dataDir, 'settings.json'), JSON.stringify({ lastVersion: OLDER }))
    const before = migrateStarted()
    const seen = logLines(dataDir).length
    const realDocker = execFileSync('sh', ['-c', 'command -v docker'], { encoding: 'utf8' }).trim()
    ;({ app, page } = await open(dataDir, { PAPERLAB_DOCKER: FAILING_PG_DUMP, REAL_DOCKER: realDocker }))
    await expect(page.getByRole('heading', { level: 1, name: 'Backup failed' })).toBeVisible({ timeout: STARTUP })
    await expect(page.locator('#detail')).toHaveText('pg_dump: error: forced by the test')
    expect(createHash('sha256').update(readFileSync(latest)).digest('hex')).toBe(backedUp)
    expect(existsSync(temp)).toBe(false)
    expect(migrateStarted()).toBe(before)
    expect(logLines(dataDir).slice(seen).some(isFullUp)).toBe(false)
  } finally {
    await app?.close().catch(() => undefined) // already exited on the happy path; still safe to call again
    rmSync(dataDir, { recursive: true, force: true })
  }
})
