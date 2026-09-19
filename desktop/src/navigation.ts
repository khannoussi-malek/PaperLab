/** Window safety (spec §5): which navigations stay in PaperLab's window, and the startup page's buttons. */

type Navigation = 'allow' | 'external' | 'deny'
export type StartupAction = 'retry' | 'show-log'

const withoutQuery = (url: string) => url.split(/[?#]/)[0]

/** PaperLab's own origin and the startup page stay; any other http or https address opens in the system browser;
 * anything else (other files, javascript:, custom schemes) goes nowhere. */
export function navigationFor(url: string, appOrigin: string, startupUrl: string): Navigation {
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return 'deny'
  }
  if (parsed.origin === appOrigin) return 'allow'
  if (parsed.protocol === 'file:') return withoutQuery(url) === withoutQuery(startupUrl) ? 'allow' : 'deny'
  return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? 'external' : 'deny'
}

/** The startup page's buttons link to the page itself with ?action=retry or ?action=show-log. */
export function startupAction(url: string, startupUrl: string): StartupAction | null {
  if (withoutQuery(url) !== withoutQuery(startupUrl)) return null
  const action = new URL(url).searchParams.get('action')
  return action === 'retry' || action === 'show-log' ? action : null
}
