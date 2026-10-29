const key = (scope: string) => `paperlab-triage-session:${scope}`
/** Used when sessionStorage is unavailable (private mode, blocked): the id then lives until the tab's script reloads. */
const memory = new Map<string, string>()

/** The scope's session id: the stored one (a reload keeps the session), else a new one. */
export function openSession(scope: string): string {
  try {
    const stored = sessionStorage.getItem(key(scope))
    if (stored) return stored
  } catch {
    // fall through to memory
  }
  const id = memory.get(scope) ?? crypto.randomUUID()
  memory.set(scope, id)
  try {
    sessionStorage.setItem(key(scope), id)
  } catch {
    // memory copy is the fallback
  }
  return id
}

export function closeSession(scope: string): void {
  memory.delete(scope)
  try {
    sessionStorage.removeItem(key(scope))
  } catch {
    // nothing stored we could remove
  }
}
