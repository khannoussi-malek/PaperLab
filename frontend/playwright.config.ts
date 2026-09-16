import { defineConfig } from '@playwright/test'

// chat-models.spec.ts marks a model default through the UI (PUT /api/llm/default), moving the one shared
// `is_default` row. Every spec using the `llmName`/`llmConnection` fixtures snapshots "the owner's default" at
// setup and restores it at teardown (fixtures.ts); if that snapshot races a concurrent default change, it
// restores the wrong model. Isolated to its own single-worker project that runs after everything else, so
// nothing else is ever mid-test while the default moves.
const DEFAULT_MOVING_SPECS = 'chat-models.spec.ts'

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
  projects: [
    {
      name: 'parallel',
      testIgnore: DEFAULT_MOVING_SPECS,
    },
    {
      name: 'default-mover',
      testMatch: DEFAULT_MOVING_SPECS,
      workers: 1,
      dependencies: ['parallel'],
    },
  ],
})
