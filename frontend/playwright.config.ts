import { defineConfig } from '@playwright/test'

// A spec that marks a model default (PUT /api/llm/default) moves the one shared `is_default` row. Every spec
// using the `llmName`/`llmConnection` fixtures snapshots "the owner's default" at setup and restores it at
// teardown (fixtures.ts); if that snapshot races a concurrent default change, it restores the wrong model. Any
// such spec carries this tag, which puts it in its own single-worker project running after everything else, so
// nothing else is ever mid-test while the default moves. A tag, not a filename: a new spec that moves the
// default says so itself instead of quietly losing the protection.
const MOVES_DEFAULT = /@moves-default/

// Runs against the real stack: `docker compose up -d` first. No mocked backend.
export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  // The run borrows the owner's own default model and leaves connections behind: these put both back even when
  // a run is killed mid-test, which no per-test teardown can cover.
  globalSetup: './e2e/globalSetup.ts',
  globalTeardown: './e2e/globalTeardown.ts',
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
      grepInvert: MOVES_DEFAULT,
    },
    {
      name: 'default-mover',
      grep: MOVES_DEFAULT,
      workers: 1,
      dependencies: ['parallel'],
    },
  ],
})
