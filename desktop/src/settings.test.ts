import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { DEFAULTS, parseSettings, readSettings, settingsFile, updateSettings } from './settings'

const dataDir = () => mkdtempSync(join(tmpdir(), 'paperlab-settings-'))

describe('settings.json', () => {
  it('starts from the defaults: stop on close, port 5190, the update check on', () => {
    expect(DEFAULTS).toEqual({
      keepRunning: false,
      port: 5190,
      updatesEnabled: true,
      dismissedUpdate: null,
      lastVersion: null,
      backedUpFrom: null,
    })
  })

  it('gives the defaults for a missing file, an unreadable one, broken JSON and JSON that is not an object', () => {
    expect(readSettings(dataDir())).toEqual(DEFAULTS)
    const unreadable = dataDir()
    mkdirSync(settingsFile(unreadable)) // a folder where the file should be
    expect(readSettings(unreadable)).toEqual(DEFAULTS)
    const broken = dataDir()
    writeFileSync(settingsFile(broken), '{"port": 51')
    expect(readSettings(broken)).toEqual(DEFAULTS)
    expect(parseSettings('[5191]')).toEqual(DEFAULTS)
  })

  it('keeps each field of the right type, and gives a wrong-typed one its own default', () => {
    const typo = { keepRunning: true, port: '5191', updatesEnabled: 'no', lastVersion: 3 }
    expect(parseSettings(JSON.stringify(typo))).toEqual({ ...DEFAULTS, keepRunning: true })
    const set = { port: 5191, updatesEnabled: false, dismissedUpdate: '0.2.0', lastVersion: '0.1.0' }
    expect(parseSettings(JSON.stringify(set))).toEqual({ ...DEFAULTS, ...set })
    expect(parseSettings('{"port": 70000}').port).toBe(5190)
    expect(parseSettings('{"port": 5191.5}').port).toBe(5190)
  })

  it('round-trips the port and the update switch through a write and a read', () => {
    const dir = join(dataDir(), 'PaperLab') // not there yet: the first write makes it
    const written = updateSettings(dir, { port: 5191, updatesEnabled: false })

    expect(written).toEqual({ ...DEFAULTS, port: 5191, updatesEnabled: false })
    expect(readSettings(dir)).toEqual(written)
    expect(updateSettings(dir, { lastVersion: '0.1.0' })).toEqual({ ...written, lastVersion: '0.1.0' })
    expect(JSON.parse(readFileSync(settingsFile(dir), 'utf8'))).toEqual({ ...written, lastVersion: '0.1.0' })
  })
})
