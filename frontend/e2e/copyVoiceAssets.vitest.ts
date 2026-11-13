import { spawnSync } from 'node:child_process'
import { copyFileSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, it } from 'vitest'

const SCRIPT = fileURLToPath(new URL('../scripts/copy-voice-assets.mjs', import.meta.url))

it('warns in one line and exits 0 when the speech detector package is not installed', () => {
  // The script finds node_modules and public/ next to its own folder, so run a copy of it in an empty project.
  const project = mkdtempSync(join(tmpdir(), 'voice-assets-'))
  try {
    mkdirSync(join(project, 'scripts'))
    copyFileSync(SCRIPT, join(project, 'scripts', 'copy-voice-assets.mjs'))
    const run = spawnSync(process.execPath, [join(project, 'scripts', 'copy-voice-assets.mjs')], { encoding: 'utf8' })
    expect(run.status).toBe(0)
    expect(run.stderr.trim().split('\n')).toHaveLength(1)
    expect(run.stderr).toMatch(/voice/i)
  } finally {
    rmSync(project, { recursive: true, force: true })
  }
})
