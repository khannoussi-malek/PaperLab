import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { fileLog, LOG_LIMIT } from './log'

const at = () => new Date('2026-09-18T10:00:00Z')
const logFile = () => join(mkdtempSync(join(tmpdir(), 'paperlab-log-')), 'logs', 'main.log')

describe('main.log', () => {
  it('appends one timestamped line per entry, making its folder', () => {
    const path = logFile()
    const log = fileLog(path, at)
    log('docker info --format {{.OSType}} → exit 0')
    log('docker compose version --short → exit 0')

    expect(readFileSync(path, 'utf8')).toBe(
      '2026-09-18T10:00:00.000Z docker info --format {{.OSType}} → exit 0\n' +
        '2026-09-18T10:00:00.000Z docker compose version --short → exit 0\n',
    )
  })

  it('starts over once the file is past 1 MB', () => {
    const path = logFile()
    fileLog(path, at)('first')
    writeFileSync(path, 'x'.repeat(LOG_LIMIT + 1))
    fileLog(path, at)('after')

    expect(readFileSync(path, 'utf8')).toBe('2026-09-18T10:00:00.000Z after\n')
  })
})
