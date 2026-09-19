/**
 * D142: before a new version first starts, a pg_dump of the library goes to <data>/backups/latest.sql.gz, replacing the
 * previous one. main.ts hands in the dump (docker.ts's dumpTo); this module decides, and handles the files.
 */
import { mkdirSync, renameSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { lastLine, type Result } from './docker'
import { compareVersions } from './updates'

export type BackupResult = { ok: true } | { ok: false; detail: string }

/** A backup only on a real upgrade: lastVersion null is a fresh install (nothing to back up yet), the same version is
 * a restart, and a downgrade goes straight to migrate and fails there (it must not dump the already-migrated
 * database over the one dump still good for going back). */
export function needsBackup(lastVersion: string | null, current: string): boolean {
  return lastVersion !== null && (compareVersions(lastVersion, current) ?? 0) < 0
}

export function backupFiles(dataDir: string) {
  const dir = join(dataDir, 'backups')
  return { dir, temp: join(dir, 'backup.sql.gz.tmp'), latest: join(dir, 'latest.sql.gz') }
}

/** The dump goes to backup.sql.gz.tmp and is renamed over latest.sql.gz only once whole, so latest is always a complete
 * dump. A failed dump removes the temporary file and leaves latest as it was. */
export async function backUp(dataDir: string, dump: (path: string) => Promise<Result>): Promise<BackupResult> {
  const { dir, temp, latest } = backupFiles(dataDir)
  try {
    mkdirSync(dir, { recursive: true })
    const result = await dump(temp)
    if (result.code !== 0 || result.timedOut) {
      rmSync(temp, { force: true })
      return { ok: false, detail: lastLine(result) ?? `pg_dump stopped with exit code ${result.code}` }
    }
    renameSync(temp, latest)
    return { ok: true }
  } catch (error) {
    rmSync(temp, { force: true })
    return { ok: false, detail: String(error) }
  }
}
