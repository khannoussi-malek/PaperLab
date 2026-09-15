import { defineConfig } from '@playwright/test'

// Runs against the real stack: `docker compose up -d` first. No mocked backend.
export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  // One real backend shared by every worker: each test makes its own papers and workspaces, so none may assume
  // it owns the whole library. `--workers=1` runs serially.
  workers: 4,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5180',
    // Fail a stuck action in seconds, so a broken UI fails fast and fixtures still clean up.
    actionTimeout: 10_000,
    trace: 'retain-on-failure',
  },
})
