import { describe, expect, it } from 'vitest'
import { chartMeta, plural, relativeTime } from './chartMeta'

const NOW = Date.parse('2026-09-20T12:00:00Z')
const ago = (seconds: number) => new Date(NOW - seconds * 1000).toISOString()

describe('plural', () => {
  it('keeps the singular at one', () => {
    expect(plural(1, 'note')).toBe('1 note')
    expect(plural(0, 'note')).toBe('0 notes')
    expect(plural(2, 'chart')).toBe('2 charts')
  })
})

describe('relativeTime', () => {
  it('says "just now" under a minute, either side of it', () => {
    expect(relativeTime(ago(0), NOW)).toBe('just now')
    expect(relativeTime(ago(59), NOW)).toBe('just now')
    expect(relativeTime(new Date(NOW + 30_000).toISOString(), NOW)).toBe('just now')
  })

  it('picks the largest unit that fits', () => {
    expect(relativeTime(ago(60), NOW)).toBe('1 minute ago')
    expect(relativeTime(ago(2 * 3600), NOW)).toBe('2 hours ago')
    expect(relativeTime(ago(3 * 86400), NOW)).toBe('3 days ago')
    expect(relativeTime(ago(2 * 7 * 86400), NOW)).toBe('2 weeks ago')
  })

  it('takes the idiomatic wording where English has one (`numeric: "auto"`)', () => {
    expect(relativeTime(ago(86400), NOW)).toBe('yesterday')
    expect(relativeTime(ago(7 * 86400), NOW)).toBe('last week')
    expect(relativeTime(ago(400 * 86400), NOW)).toBe('last year')
  })
})

describe('chartMeta', () => {
  it('reads as one line, with the note count in the right number', () => {
    expect(chartMeta({ note_count: 1, updated_at: ago(3600) }, NOW)).toBe('Used in 1 note · edited 1 hour ago')
    expect(chartMeta({ note_count: 0, updated_at: ago(10) }, NOW)).toBe('Used in 0 notes · edited just now')
  })
})
