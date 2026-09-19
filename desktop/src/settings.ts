/**
 * The app's own settings, in <data>/settings.json (spec §5). `port` lives here because an environment variable never
 * reaches an app started from Finder or the Start menu; `lastVersion` is the version that last started, for the backup.
 */
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

export type Settings = {
  keepRunning: boolean
  port: number
  updatesEnabled: boolean
  dismissedUpdate: string | null
  lastVersion: string | null
  /** The lastVersion a backup has already been taken for this upgrade from (D142): lets a retry skip backing up
   * again over the dump it already took. Cleared once the new version starts. */
  backedUpFrom: string | null
}

export const DEFAULTS: Settings = {
  keepRunning: false,
  port: 5190,
  updatesEnabled: true,
  dismissedUpdate: null,
  lastVersion: null,
  backedUpFrom: null,
}

const isPort = (value: unknown): value is number => Number.isInteger(value) && (value as number) >= 1 && (value as number) <= 65535
const isTextOrNull = (value: unknown): value is string | null => value === null || typeof value === 'string'

function fields(text: string): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(text)
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {}
  } catch {
    return {} // not JSON: every field takes its default
  }
}

/** Each field of the right type is kept; a missing or wrong-typed one takes its own default, and the others stay. */
export function parseSettings(text: string): Settings {
  const raw = fields(text)
  return {
    keepRunning: typeof raw.keepRunning === 'boolean' ? raw.keepRunning : DEFAULTS.keepRunning,
    port: isPort(raw.port) ? raw.port : DEFAULTS.port,
    updatesEnabled: typeof raw.updatesEnabled === 'boolean' ? raw.updatesEnabled : DEFAULTS.updatesEnabled,
    dismissedUpdate: isTextOrNull(raw.dismissedUpdate) ? raw.dismissedUpdate : DEFAULTS.dismissedUpdate,
    lastVersion: isTextOrNull(raw.lastVersion) ? raw.lastVersion : DEFAULTS.lastVersion,
    backedUpFrom: isTextOrNull(raw.backedUpFrom) ? raw.backedUpFrom : DEFAULTS.backedUpFrom,
  }
}

export const settingsFile = (dataDir: string) => join(dataDir, 'settings.json')

/** A missing or unreadable file gives the defaults (a first launch has none). */
export function readSettings(dataDir: string): Settings {
  try {
    return parseSettings(readFileSync(settingsFile(dataDir), 'utf8'))
  } catch {
    return DEFAULTS
  }
}

/** The settings with `patch` applied, written whole (a temp file renamed over the old one) and returned. */
export function updateSettings(dataDir: string, patch: Partial<Settings>): Settings {
  const next = { ...readSettings(dataDir), ...patch }
  mkdirSync(dataDir, { recursive: true })
  const temp = `${settingsFile(dataDir)}.tmp`
  writeFileSync(temp, `${JSON.stringify(next, null, 2)}\n`)
  renameSync(temp, settingsFile(dataDir))
  return next
}
