// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { GLOSSARY } from './glossary'
import { Term } from './Term'

// jsdom has no ResizeObserver, which Radix popper content asks for
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

describe('Term', () => {
  it('opens its explanation on keyboard focus', () => {
    render(<Term term="prisma">PRISMA</Term>)
    const trigger = screen.getByRole('button', { name: /PRISMA/ })
    act(() => trigger.focus())
    const tip = screen.getByRole('tooltip')
    expect(tip).toHaveTextContent(GLOSSARY.prisma)
    expect(trigger.getAttribute('aria-describedby')).toBe(screen.getByText(GLOSSARY.prisma, { selector: '[data-slot=tooltip-content]' }).id)
  })

  it('waits about 300 ms on hover, and has a visible focus ring', () => {
    vi.useFakeTimers()
    try {
      render(<Term term="run">Run</Term>)
      const trigger = screen.getByRole('button', { name: /Run/ })
      expect(trigger.className).toContain('focus-visible:ring-3')
      fireEvent.pointerMove(trigger)
      act(() => { vi.advanceTimersByTime(200) })
      expect(screen.queryByRole('tooltip')).toBeNull()
      act(() => { vi.advanceTimersByTime(150) })
      expect(screen.getByRole('tooltip')).toHaveTextContent(GLOSSARY.run)
    } finally {
      vi.useRealTimers()
    }
  })

  it('opens on tap and closes on a second tap', () => {
    render(<Term term="run">Run</Term>)
    const trigger = screen.getByRole('button', { name: /Run/ })
    fireEvent.click(trigger)
    expect(screen.getByRole('tooltip')).toHaveTextContent(GLOSSARY.run)
    fireEvent.click(trigger)
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('a tap inside a clickable parent does not reach the parent', () => {
    const spy = vi.fn()
    render(<div onClick={spy}><Term term="run">Run</Term></div>)
    fireEvent.click(screen.getByRole('button', { name: /Run/ }))
    expect(spy).not.toHaveBeenCalled()
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
  })

  it('every glossary key is used', () => {
    // Placed as term="<key>" in JSX, or named as a quoted key in a data table (the PRISMA rows) that feeds a Term.
    const modules = import.meta.glob(['/src/**/*.ts', '/src/**/*.tsx'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>
    const sources = Object.entries(modules)
      .filter(([path]) => !/\.test\.tsx?$|glossary\.ts$|schema\.d\.ts$/.test(path))
      .map(([, src]) => src)
    const unused = Object.keys(GLOSSARY).filter((key) => !sources.some((src) => src.includes(`term="${key}"`) || src.includes(`'${key}'`)))
    expect(unused).toEqual([])
  })
})
