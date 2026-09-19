/**
 * P8 (D141): once per launch, the app asks GitHub for the latest release and offers a newer one. main.ts runs it only in
 * a packaged app and only while Settings' switch is on; a failure is logged, never shown.
 */
import type { Log } from './log'

export const LATEST_RELEASE = 'https://api.github.com/repos/khannoussi-malek/PaperLab/releases/latest'

/** The release page, built from a checked version rather than taken from the answer. */
const releasePage = (version: string) => `https://github.com/khannoussi-malek/PaperLab/releases/tag/v${version}`

type Version = { core: number[]; pre: string[] }

function parse(version: string): Version | null {
  const found = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/.exec(version.trim())
  if (!found) return null
  return { core: [Number(found[1]), Number(found[2]), Number(found[3])], pre: found[4] ? found[4].split('.') : [] }
}

function comparePre(a: string[], b: string[]): number {
  if (a.length === 0 || b.length === 0) return b.length - a.length // a release is above its pre-releases
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i] === b[i]) continue
    const [numberA, numberB] = [/^\d+$/.test(a[i]), /^\d+$/.test(b[i])]
    if (numberA && numberB) return Number(a[i]) - Number(b[i])
    if (numberA !== numberB) return numberA ? -1 : 1 // numbers sort before words
    return a[i] < b[i] ? -1 : 1
  }
  return a.length - b.length
}

/** Semver order (0.10.0 > 0.9.1, 1.0.0-beta.2 < 1.0.0-beta.10 < 1.0.0); null when either isn't a version. */
export function compareVersions(a: string, b: string): number | null {
  const [x, y] = [parse(a), parse(b)]
  if (x === null || y === null) return null
  const core = x.core.map((part, i) => part - y.core[i]).find((difference) => difference !== 0)
  return core ?? comparePre(x.pre, y.pre)
}

export type Update = { version: string; url: string }
export type Fetch = (url: string, init: RequestInit) => Promise<Pick<Response, 'ok' | 'status' | 'json'>>
export type UpdateCheck = { enabled: boolean; current: string; dismissed: string | null; fetch: Fetch; log: Log }

/** A newer release not put off with Later, or null. Off → no request at all. Never throws. */
export async function checkForUpdate({ enabled, current, dismissed, fetch, log }: UpdateCheck): Promise<Update | null> {
  if (!enabled) return null
  try {
    const response = await fetch(LATEST_RELEASE, {
      headers: { Accept: 'application/vnd.github+json', 'Cache-Control': 'no-cache' },
      signal: AbortSignal.timeout(10_000),
    })
    if (!response.ok) {
      log(`update check: GitHub answered ${response.status}`)
      return null
    }
    const tag = ((await response.json()) as { tag_name?: unknown }).tag_name
    const version = typeof tag === 'string' ? tag.replace(/^v/, '') : ''
    if ((compareVersions(version, current) ?? 0) <= 0 || version === dismissed) return null
    return { version, url: releasePage(version) }
  } catch (error) {
    log(`update check failed: ${String(error)}`)
    return null
  }
}
