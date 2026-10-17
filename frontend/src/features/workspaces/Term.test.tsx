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

  // Turned on in Task 13, once Terms are placed across the tabs: every GLOSSARY key appears as term="<key>" in a non-test src .tsx.
  it.todo('every glossary key is used')
})
