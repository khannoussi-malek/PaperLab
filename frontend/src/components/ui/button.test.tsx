// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Button } from './button'

// Liquid glass buttons (see "Glass" in design-system/MASTER.md). jsdom draws nothing, so these pin the classes that
// make the look; the screenshots in both themes are the real check.
const classesOf = (variant: Parameters<typeof Button>[0]['variant']) => {
  const { unmount } = render(<Button variant={variant}>Save</Button>)
  const classes = screen.getByRole('button', { name: 'Save' }).className
  unmount()
  return classes
}

describe('Button as liquid glass', () => {
  it('primary is tinted glass: solid primary for contrast, a lit top edge and a sheen', () => {
    const classes = classesOf('default')
    expect(classes).toContain('bg-primary')
    expect(classes).toMatch(/inset-shadow-\[/)
    expect(classes).toMatch(/bg-linear-to-b/)
  })

  it('outline and secondary are clear glass with a lit edge, not flat fills', () => {
    for (const variant of ['outline', 'secondary'] as const) {
      const classes = classesOf(variant)
      expect(classes).toMatch(/\bbg-glass/)
      expect(classes).toMatch(/inset-shadow-\[/)
      expect(classes).not.toMatch(/\bbg-background\b|\bbg-secondary\b/)
    }
  })

  it('ghost stays bare until hovered, then becomes glass', () => {
    const classes = classesOf('ghost')
    expect(classes).toContain('hover:bg-glass-strong')
    expect(classes).not.toMatch(/(^|\s)bg-glass/)
  })

  it('presses in like glass (a small scale) instead of nudging down, and only when motion is allowed', () => {
    const classes = classesOf('outline')
    expect(classes).toContain('motion-safe:active:not-aria-[haspopup]:scale-[0.97]')
    expect(classes).not.toContain('translate-y-px')
  })
})
