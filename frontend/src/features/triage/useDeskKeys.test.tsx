// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useRef } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDeskKeys, type DeskKeyHandlers } from './useDeskKeys'

afterEach(cleanup)

const spies = (over: Partial<DeskKeyHandlers> = {}) => ({
  reasonsShowing: false, helpOpen: false,
  onPile: vi.fn(), onReason: vi.fn(), cancelReason: vi.fn(), closeHelp: vi.fn(), exit: vi.fn(),
  undo: vi.fn(), togglePdf: vi.fn(), openHelp: vi.fn(), focusAbstract: vi.fn(),
  ...over,
}) satisfies DeskKeyHandlers

function Desk({ h }: { h: DeskKeyHandlers }) {
  const ref = useRef<HTMLElement>(null)
  useDeskKeys(ref, h)
  return (
    <section ref={ref} tabIndex={0} data-testid="root">
      <article data-triage-card data-testid="card"><h2>t</h2></article>
      <button data-testid="button">b</button>
      <div aria-label="Abstract" tabIndex={0} data-testid="abstract">a</div>
      <input data-testid="input" aria-label="Note" />
      <div data-triage-pdf tabIndex={0} data-testid="pdf"><span data-testid="pdfText">p</span></div>
      <div data-triage-region tabIndex={-1} data-testid="r1">1</div>
      <div data-triage-region tabIndex={-1} data-testid="r2">2</div>
    </section>
  )
}

const FREE = ['root', 'card'] as const
const OWN = ['button', 'abstract', 'pdf', 'pdfText'] as const
type Init = KeyboardEventInit
const KEYS: [string, Init, keyof DeskKeyHandlers, unknown[]][] = [
  ['ArrowRight', { key: 'ArrowRight' }, 'onPile', ['read_closely']],
  ['ArrowDown', { key: 'ArrowDown' }, 'onPile', ['skim']],
  ['ArrowUp', { key: 'ArrowUp' }, 'onPile', ['later']],
  ['ArrowLeft', { key: 'ArrowLeft' }, 'onPile', ['not_relevant']],
  ['1', { key: '1' }, 'onPile', ['read_closely']],
  ['4', { key: '4' }, 'onPile', ['not_relevant']],
  ['5', { key: '5' }, 'onPile', ['skip']],
  ['Space', { key: ' ' }, 'onPile', ['skip']],
]
const ALWAYS: [string, Init, keyof DeskKeyHandlers][] = [
  ['p', { key: 'p' }, 'togglePdf'], ['u', { key: 'u' }, 'undo'], ['?', { key: '?', shiftKey: true }, 'openHelp'], ['Esc', { key: 'Escape' }, 'exit'],
  ['Cmd+Z', { key: 'z', metaKey: true }, 'undo'], ['Ctrl+Z', { key: 'z', ctrlKey: true }, 'undo'],
]
const fire = (id: string, init: Init) => fireEvent.keyDown(screen.getByTestId(id), init)
const called = (h: DeskKeyHandlers) => Object.entries(h).filter(([, v]) => typeof v === 'function' && (v as ReturnType<typeof vi.fn>).mock.calls.length).map(([k]) => k)

describe('key table', () => {
  for (const target of FREE) {
    it.each(KEYS)(`${target}: %s is a pile key`, (_n, init, fn, args) => {
      const h = spies(); render(<Desk h={h} />)
      fire(target, init)
      expect(called(h)).toEqual([fn])
      expect(h[fn as 'onPile']).toHaveBeenCalledWith(...args)
    })
    it(`${target}: A focuses the abstract`, () => {
      const h = spies(); render(<Desk h={h} />)
      fire(target, { key: 'a' })
      expect(called(h)).toEqual(['focusAbstract'])
    })
  }
  for (const target of OWN) {
    it.each(KEYS)(`${target}: %s belongs to the element`, (_n, init) => {
      const h = spies(); render(<Desk h={h} />)
      fire(target, init)
      expect(called(h)).toEqual([])
    })
    it(`${target}: A belongs to the element`, () => {
      const h = spies(); render(<Desk h={h} />)
      fire(target, { key: 'a' })
      expect(called(h)).toEqual([])
    })
  }
  for (const target of [...FREE, ...OWN]) {
    it.each(ALWAYS)(`${target}: %s is a desk key`, (_n, init, fn) => {
      const h = spies(); render(<Desk h={h} />)
      fire(target, init)
      expect(called(h)).toEqual([fn])
    })
  }
})

it('inside a text input only Esc is the desk\'s (letters, digits and undo stay typing)', () => {
  const h = spies(); render(<Desk h={h} />)
  for (const init of [{ key: 'p' }, { key: 'u' }, { key: '?', shiftKey: true }, { key: '1' }, { key: 'ArrowLeft' }, { key: ' ' }, { key: 'z', metaKey: true }]) fire('input', init)
  expect(called(h)).toEqual([])
  fire('input', { key: 'Escape' })
  expect(called(h)).toEqual(['exit'])
})

it('other chords and held keys are ignored', () => {
  const h = spies(); render(<Desk h={h} />)
  fire('root', { key: 'ArrowLeft', altKey: true })
  fire('root', { key: '1', ctrlKey: true })
  fire('root', { key: 'p', metaKey: true })
  fire('root', { key: 'ArrowLeft', shiftKey: true })
  fire('root', { key: '1', repeat: true })
  expect(called(h)).toEqual([])
})

it('Esc order: a pending reason first, then the help, then exit', () => {
  let h = spies({ reasonsShowing: true, helpOpen: true }); const { unmount } = render(<Desk h={h} />)
  fire('root', { key: 'Escape' })
  expect(called(h)).toEqual(['cancelReason'])
  unmount()
  h = spies({ helpOpen: true }); render(<Desk h={h} />)
  fire('root', { key: 'Escape' })
  expect(called(h)).toEqual(['closeHelp'])
})

it('while the chip row shows, 1-6 are reasons and the other pile keys do nothing', () => {
  const h = spies({ reasonsShowing: true }); render(<Desk h={h} />)
  fire('root', { key: '6' })
  expect(h.onReason).toHaveBeenCalledWith(6)
  fire('root', { key: 'ArrowRight' })
  fire('root', { key: ' ' })
  expect(h.onPile).not.toHaveBeenCalled()
})

it('F6 and Shift+F6 cycle the regions', () => {
  render(<Desk h={spies()} />)
  fire('root', { key: 'F6' })
  expect(screen.getByTestId('r1')).toHaveFocus()
  fire('r1', { key: 'F6' })
  expect(screen.getByTestId('r2')).toHaveFocus()
  fire('r2', { key: 'F6', shiftKey: true })
  expect(screen.getByTestId('r1')).toHaveFocus()
})

it('a handled key is prevented, and one keydown is handled once', () => {
  const h = spies(); render(<Desk h={h} />)
  const ev = new KeyboardEvent('keydown', { key: '1', bubbles: true, cancelable: true })
  screen.getByTestId('root').dispatchEvent(ev)
  expect(ev.defaultPrevented).toBe(true)
  expect(h.onPile).toHaveBeenCalledTimes(1)
})
