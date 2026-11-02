// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useRef } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDeskKeys, type DeskKeyHandlers } from './useDeskKeys'

afterEach(cleanup)

const spies = (over: Partial<DeskKeyHandlers> = {}) => ({
  reasonsShowing: false, lateShowing: false, fiveCsOpen: false, helpOpen: false,
  onPile: vi.fn(), onReason: vi.fn(), cancelReason: vi.fn(), closeHelp: vi.fn(), exit: vi.fn(),
  toggleFiveCs: vi.fn(), onTick: vi.fn(),
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
  ['p', { key: 'p' }, 'togglePdf'], ['u', { key: 'u' }, 'undo'], ['?', { key: '?', shiftKey: true }, 'openHelp'],
  ['Cmd+Z', { key: 'z', metaKey: true }, 'undo'], ['Ctrl+Z', { key: 'z', ctrlKey: true }, 'undo'],
]
const fire = (id: string, init: Init) => fireEvent.keyDown(screen.getByTestId(id), init)
const firstArgs = (f: unknown) => (f as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0])
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

it('Esc exits from the desk, the card, a button and a field', () => {
  for (const id of ['root', 'card', 'button', 'input']) {
    const h = spies(); const { unmount } = render(<Desk h={h} />)
    fire(id, { key: 'Escape' })
    expect(called(h)).toEqual(['exit'])
    unmount()
  }
})

it('Esc in the PDF column or the abstract returns focus to the desk and does not exit', () => {
  for (const id of ['pdf', 'pdfText', 'abstract']) {
    const h = spies(); const { unmount } = render(<Desk h={h} />)
    screen.getByTestId(id).focus()
    fire(id, { key: 'Escape' })
    expect(called(h)).toEqual([])
    expect(screen.getByTestId('root')).toHaveFocus()
    unmount()
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

describe('the five Cs', () => {
  it('C toggles them from the desk and the card, not from a button, the abstract or the PDF', () => {
    for (const id of FREE) {
      const h = spies(); const { unmount } = render(<Desk h={h} />)
      fire(id, { key: 'c' })
      fire(id, { key: 'C' })
      expect(h.toggleFiveCs).toHaveBeenCalledTimes(2)
      unmount()
    }
    for (const id of OWN) {
      const h = spies(); const { unmount } = render(<Desk h={h} />)
      fire(id, { key: 'c' })
      expect(called(h)).toEqual([])
      unmount()
    }
  })

  it('Cmd+C stays the browser\'s copy', () => {
    const h = spies(); render(<Desk h={h} />)
    const ev = new KeyboardEvent('keydown', { key: 'c', metaKey: true, bubbles: true, cancelable: true })
    screen.getByTestId('root').dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(false)
    expect(called(h)).toEqual([])
  })

  it('open: 1 to 5 tick and arrows and Space still decide; 6 is nothing', () => {
    const h = spies({ fiveCsOpen: true }); render(<Desk h={h} />)
    for (const k of ['1', '2', '3', '4', '5', '6']) fire('root', { key: k })
    expect(firstArgs(h.onTick)).toEqual([1, 2, 3, 4, 5])
    expect(h.onPile).not.toHaveBeenCalled()
    fire('root', { key: 'ArrowRight' })
    fire('root', { key: ' ' })
    expect(firstArgs(h.onPile)).toEqual(['read_closely', 'skip'])
  })

  it('closed: 1 to 5 are piles, and a held digit does not tick twice', () => {
    const h = spies(); render(<Desk h={h} />)
    fire('root', { key: '1' })
    expect(h.onTick).not.toHaveBeenCalled()
    expect(h.onPile).toHaveBeenCalledWith('read_closely')
    const open = spies({ fiveCsOpen: true }); cleanup(); render(<Desk h={open} />)
    fire('root', { key: '1', repeat: true })
    expect(open.onTick).not.toHaveBeenCalled()
  })

  it('open: a tick shows no held-key stamp', () => {
    const onHold = vi.fn(); const h = spies({ fiveCsOpen: true, onHold }); render(<Desk h={h} />)
    fire('root', { key: '1' })
    expect(onHold).not.toHaveBeenCalled()
  })

  it('the required chips outrank them: digits are reasons and C sleeps', () => {
    const h = spies({ fiveCsOpen: true, reasonsShowing: true }); render(<Desk h={h} />)
    fire('root', { key: '2' })
    fire('root', { key: 'c' })
    expect(h.onReason).toHaveBeenCalledWith(2)
    expect(h.onTick).not.toHaveBeenCalled()
    expect(h.toggleFiveCs).not.toHaveBeenCalled()
  })

  it('Esc order: reason, help, out of a scroller, then the checklist, then leave', () => {
    const cases: [Partial<DeskKeyHandlers>, string, string[]][] = [
      [{ fiveCsOpen: true, reasonsShowing: true }, 'root', ['cancelReason']],
      [{ fiveCsOpen: true, helpOpen: true }, 'root', ['closeHelp']],
      [{ fiveCsOpen: true }, 'abstract', []],
      [{ fiveCsOpen: true }, 'root', ['toggleFiveCs']],
      [{ fiveCsOpen: true }, 'button', ['toggleFiveCs']],
      [{}, 'root', ['exit']],
    ]
    for (const [over, id, want] of cases) {
      const h = spies(over); const { unmount } = render(<Desk h={h} />)
      fire(id, { key: 'Escape' })
      expect(called(h)).toEqual(want)
      unmount()
    }
  })
})

describe('the optional chips', () => {
  it('while the row shows, 7 to 9 pick chips 1 to 3 and 1 to 5 stay pile keys', () => {
    const h = spies({ lateShowing: true }); render(<Desk h={h} />)
    for (const k of ['7', '8', '9']) fire('root', { key: k })
    expect(firstArgs(h.onReason)).toEqual([1, 2, 3])
    fire('root', { key: '1' })
    fire('root', { key: 'ArrowDown' })
    expect(firstArgs(h.onPile)).toEqual(['read_closely', 'skim'])
    expect(h.onReason).toHaveBeenCalledTimes(3)
  })

  it('without the row 7 to 9 do nothing and are left to the browser', () => {
    const h = spies(); render(<Desk h={h} />)
    const ev = new KeyboardEvent('keydown', { key: '7', bubbles: true, cancelable: true })
    screen.getByTestId('root').dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(false)
    expect(called(h)).toEqual([])
  })

  it('7 to 9 belong to a focused button like every other pile key, and a held one acts once', () => {
    const h = spies({ lateShowing: true }); render(<Desk h={h} />)
    fire('button', { key: '7' })
    fire('root', { key: '7', repeat: true })
    expect(h.onReason).not.toHaveBeenCalled()
  })
})
