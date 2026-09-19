import { describe, expect, it } from 'vitest'
import { checkForUpdate, compareVersions, LATEST_RELEASE, type Fetch } from './updates'

describe('compareVersions', () => {
  it('orders by number, not by text, with or without a v', () => {
    expect(compareVersions('0.10.0', '0.9.1')).toBeGreaterThan(0)
    expect(compareVersions('0.9.1', '0.10.0')).toBeLessThan(0)
    expect(compareVersions('v1.2.3', '1.2.3')).toBe(0)
  })

  it('puts a pre-release below its release, and orders pre-releases by their parts', () => {
    expect(compareVersions('1.0.0-beta.2', '1.0.0')).toBeLessThan(0)
    expect(compareVersions('1.0.0', '1.0.0-rc.1')).toBeGreaterThan(0)
    expect(compareVersions('1.0.0-beta.2', '1.0.0-beta.10')).toBeLessThan(0)
    expect(compareVersions('1.0.0-alpha', '1.0.0-beta')).toBeLessThan(0)
  })

  it('is null for anything that is not a version', () => {
    expect(compareVersions('dev', '0.1.0')).toBeNull()
    expect(compareVersions('0.1', '0.1.0')).toBeNull()
  })
})

type Asked = { url: string; init: RequestInit }

function github(answer: { ok: boolean; status: number; body?: unknown } | Error) {
  const asked: Asked[] = []
  const fetch: Fetch = async (url, init) => {
    asked.push({ url, init })
    if (answer instanceof Error) throw answer
    return { ok: answer.ok, status: answer.status, json: async () => answer.body }
  }
  return { fetch, asked }
}

const released = (tag: string) => github({ ok: true, status: 200, body: { tag_name: tag } })
const check = (fetch: Fetch, more: Partial<Parameters<typeof checkForUpdate>[0]> = {}) =>
  checkForUpdate({ enabled: true, current: '0.1.0', dismissed: null, fetch, log: () => {}, ...more })

describe('checkForUpdate', () => {
  it("offers a newer release, with its page on PaperLab's GitHub", async () => {
    expect(await check(released('v0.2.0').fetch)).toEqual({
      version: '0.2.0',
      url: 'https://github.com/khannoussi-malek/PaperLab/releases/tag/v0.2.0',
    })
  })

  it('offers nothing for the same or an older release, or for one put off with Later', async () => {
    expect(await check(released('v0.1.0').fetch)).toBeNull()
    expect(await check(released('v0.0.9').fetch)).toBeNull()
    expect(await check(released('v0.2.0').fetch, { dismissed: '0.2.0' })).toBeNull()
  })

  it('asks GitHub for the latest release, without a cached answer', async () => {
    const { fetch, asked } = released('v0.1.0')
    await check(fetch)

    expect(asked.map(({ url }) => url)).toEqual([LATEST_RELEASE])
    expect(new Headers(asked[0].init.headers).get('cache-control')).toBe('no-cache')
  })

  it('logs a refusal or a failed request, and never throws', async () => {
    const lines: string[] = []
    const log = (line: string) => void lines.push(line)

    expect(await check(github({ ok: false, status: 403 }).fetch, { log })).toBeNull()
    expect(await check(github(new TypeError('fetch failed')).fetch, { log })).toBeNull()
    expect(lines).toEqual(['update check: GitHub answered 403', 'update check failed: TypeError: fetch failed'])
  })

  it('asks nothing at all while the switch is off', async () => {
    const { fetch, asked } = released('v9.0.0')

    expect(await check(fetch, { enabled: false })).toBeNull()
    expect(asked).toEqual([])
  })
})
