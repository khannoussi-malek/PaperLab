import { existsSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { backUp, backupFiles, needsBackup } from './backup'
import type { Result } from './docker'

const dataDir = () => mkdtempSync(join(tmpdir(), 'paperlab-backup-'))
const done = (more: Partial<Result> = {}): Result => ({ code: 0, stdout: '', stderr: '', timedOut: false, ...more })
/** A pg_dump that writes `content` where it is told to, then answers `result`. */
const writes = (content: string, result: Result = done()) => async (path: string) => {
  writeFileSync(path, content)
  return result
}

describe('needsBackup', () => {
  it('backs up only when another version used this library: never on a fresh install or a restart', () => {
    expect(needsBackup(null, '0.2.0')).toBe(false)
    expect(needsBackup('0.2.0', '0.2.0')).toBe(false)
    expect(needsBackup('0.1.0', '0.2.0')).toBe(true)
  })
})

describe('backUp', () => {
  it('dumps under a temporary name, then renames it over latest.sql.gz', async () => {
    const dir = dataDir()
    const { temp, latest } = backupFiles(dir)
    const told: string[] = []

    const result = await backUp(dir, async (path) => {
      told.push(path)
      writeFileSync(path, 'new dump')
      expect(existsSync(latest)).toBe(false) // nothing is renamed before the dump is whole
      return done()
    })

    expect(result).toEqual({ ok: true })
    expect(told).toEqual([join(dir, 'backups', 'backup.sql.gz.tmp')])
    expect(readFileSync(join(dir, 'backups', 'latest.sql.gz'), 'utf8')).toBe('new dump')
    expect(existsSync(temp)).toBe(false)
  })

  it("replaces the previous version's backup rather than keeping it", async () => {
    const dir = dataDir()

    await backUp(dir, writes('first'))
    await backUp(dir, writes('second'))

    expect(readdirSync(join(dir, 'backups'))).toEqual(['latest.sql.gz'])
    expect(readFileSync(backupFiles(dir).latest, 'utf8')).toBe('second')
  })

  it("keeps the last good backup when pg_dump fails, and says pg_dump's last line", async () => {
    const dir = dataDir()
    await backUp(dir, writes('good'))

    const failed = await backUp(dir, writes('half a dump', done({ code: 1, stderr: 'pg_dump: error: connection to server failed\n' })))

    expect(failed).toEqual({ ok: false, detail: 'pg_dump: error: connection to server failed' })
    expect(readFileSync(backupFiles(dir).latest, 'utf8')).toBe('good')
    expect(existsSync(backupFiles(dir).temp)).toBe(false)
  })
})
