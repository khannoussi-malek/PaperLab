// What the site reads from the GitHub API at build time. Each answer is null when GitHub doesn't give one:
// a missing number or version never fails a build, the page just shows less.

async function getJson(url: string, fetchImpl: typeof fetch, token?: string): Promise<Record<string, unknown> | null> {
  const headers: Record<string, string> = { Accept: 'application/vnd.github+json' }
  if (token) headers.Authorization = `Bearer ${token}`
  try {
    const response = await fetchImpl(url, { headers })
    return response.ok ? await response.json() : null
  } catch {
    return null
  }
}

/** The repository's star count. */
export async function fetchStars(repo: string, fetchImpl: typeof fetch = fetch, token?: string): Promise<number | null> {
  const count = (await getJson(`https://api.github.com/repos/${repo}`, fetchImpl, token))?.stargazers_count
  return Number.isInteger(count) ? (count as number) : null
}

/** The latest release's version, "0.2.0" for tag v0.2.0. It goes into a shell command, so only a plain version passes. */
export async function fetchLatestVersion(
  repo: string,
  fetchImpl: typeof fetch = fetch,
  token?: string,
): Promise<string | null> {
  const tag = (await getJson(`https://api.github.com/repos/${repo}/releases/latest`, fetchImpl, token))?.tag_name
  const version = typeof tag === 'string' ? tag.replace(/^v/, '') : ''
  return /^\d+\.\d+\.\d+$/.test(version) ? version : null
}

/** 5 → "5", 1234 → "1.2k". */
export function formatStars(count: number): string {
  if (count < 1000) return String(count)
  return `${Number((count / 1000).toFixed(1))}k`
}
