import { defineConfig } from '@playwright/test'

// The desktop app's window through Playwright's Electron support. `stub` needs nothing running: a stub docker answers
// (e2e/stub-docker.sh). `release-stack` drives the real release stack (README, Development) and exists only with
// E2E_RELEASE=1, so a plain `npm run e2e` never starts it.
const RELEASE_STACK = /@release-stack/

export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  workers: 1,
  use: { trace: 'retain-on-failure' },
  projects: [
    { name: 'stub', grepInvert: RELEASE_STACK },
    ...(process.env.E2E_RELEASE === '1' ? [{ name: 'release-stack', grep: RELEASE_STACK, timeout: 10 * 60_000 }] : []),
  ],
})
