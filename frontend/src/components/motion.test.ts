import { afterEach, describe, expect, it, vi } from 'vitest'
import { isFresh, withViewTransition } from './motion'

describe('isFresh', () => {
  const now = Date.parse('2026-09-14T12:00:10Z')

  it('is true for something created in the last few seconds, so it animates in once', () => {
    expect(isFresh('2026-09-14T12:00:08Z', now)).toBe(true)
  })

  it('is false for something loaded from earlier, so a reload or a filter change stays still', () => {
    expect(isFresh('2026-09-14T11:59:00Z', now)).toBe(false)
    expect(isFresh('2026-01-01T00:00:00Z', now)).toBe(false)
  })

  it('is false for a timestamp it cannot read', () => {
    expect(isFresh('not a date', now)).toBe(false)
  })
})

describe('withViewTransition', () => {
  afterEach(() => vi.unstubAllGlobals())

  /** A browser with or without the View Transitions API, and with or without "reduce motion" set. */
  function browser({ api, reduceMotion }: { api: boolean; reduceMotion: boolean }) {
    const startViewTransition = vi.fn((update: () => void) => update())
    vi.stubGlobal('document', api ? { startViewTransition } : {})
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: reduceMotion && query === '(prefers-reduced-motion: reduce)' }))
    return startViewTransition
  }

  it('runs the update inside a view transition, so the browser cross-fades old into new', () => {
    const start = browser({ api: true, reduceMotion: false })
    const update = vi.fn()
    withViewTransition(update)
    expect(start).toHaveBeenCalledOnce()
    expect(update).toHaveBeenCalledOnce()
  })

  it('just runs the update when the OS asks for reduced motion', () => {
    const start = browser({ api: true, reduceMotion: true })
    const update = vi.fn()
    withViewTransition(update)
    expect(start).not.toHaveBeenCalled()
    expect(update).toHaveBeenCalledOnce()
  })

  it('just runs the update in a browser without view transitions', () => {
    browser({ api: false, reduceMotion: false })
    const update = vi.fn()
    withViewTransition(update)
    expect(update).toHaveBeenCalledOnce()
  })
})
