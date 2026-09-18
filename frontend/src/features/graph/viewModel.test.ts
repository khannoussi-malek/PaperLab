import { describe, expect, it } from 'vitest'
import { hasWebGL, readView, VIEW_KEY, VIEW_LABELS, VIEWS, WEBGL_OFF, writeView } from './viewModel'

const memoryStorage = (initial: Record<string, string> = {}) => {
  const data = new Map(Object.entries(initial))
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
  }
}

const blockedStorage = {
  getItem: (): string | null => {
    throw new Error('blocked')
  },
  setItem: () => {
    throw new Error('blocked')
  },
}

describe('the view switcher', () => {
  it('offers the five views in the spec’s order and words', () => {
    expect(VIEWS.map((view) => VIEW_LABELS[view])).toEqual(['2D', '3D', 'Matrix', 'Timeline', 'Rings'])
  })

  it('remembers the chosen view in this browser, under its own key', () => {
    const storage = memoryStorage()
    writeView(storage, 'timeline')
    expect(VIEW_KEY).toBe('paperlab.graph.view')
    expect(storage.getItem('paperlab.graph.view')).toBe('timeline')
    expect(readView(storage)).toBe('timeline')
  })

  it('opens on 2D with nothing stored, junk stored, no storage, or storage that throws', () => {
    expect(readView(memoryStorage())).toBe('2d')
    // 'toString' is on every object's prototype: a view is one of the five, not any key that `in` would accept.
    expect(readView(memoryStorage({ [VIEW_KEY]: 'toString' }))).toBe('2d')
    expect(readView(undefined)).toBe('2d')
    expect(readView(blockedStorage)).toBe('2d')
    expect(() => writeView(blockedStorage, 'matrix')).not.toThrow()
  })
})

describe('the 3D view’s WebGL check', () => {
  const browserWith = (getContext: (kind: string) => unknown) =>
    ({ createElement: () => ({ getContext }) }) as unknown as Pick<Document, 'createElement'>

  it('accepts WebGL 2', () => {
    expect(hasWebGL(browserWith((kind) => (kind === 'webgl2' ? {} : null)))).toBe(true)
  })

  it('says no, without throwing, when only WebGL 1 is offered, both are off, or asking throws', () => {
    expect(hasWebGL(browserWith((kind) => (kind === 'webgl' ? {} : null)))).toBe(false)
    expect(hasWebGL(browserWith(() => null))).toBe(false)
    expect(
      hasWebGL(
        browserWith(() => {
          throw new Error('blocked')
        })
      )
    ).toBe(false)
    expect(WEBGL_OFF).toBe('3D needs WebGL, which this browser has turned off. The other views work without it.')
  })

  it('releases the probe context instead of leaking it toward the browser’s live-context cap', () => {
    let lost = false
    const context = {
      getExtension: (name: string) => (name === 'WEBGL_lose_context' ? { loseContext: () => (lost = true) } : null),
    }
    expect(hasWebGL(browserWith((kind) => (kind === 'webgl2' ? context : null)))).toBe(true)
    expect(lost).toBe(true)
  })
})
