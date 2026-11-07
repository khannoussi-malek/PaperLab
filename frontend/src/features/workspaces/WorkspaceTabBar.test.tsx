// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LiquidGlassProvider } from '@/components/liquid-glass/LiquidGlass'
import { Tabs } from '@/components/ui/tabs'
import type { WorkspaceTab } from '@/lib/route'
import { WorkspaceTabBar } from './WorkspaceTabBar'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

// jsdom lays nothing out: place each tab 100 px after the one before it, 80 px wide and 32 px tall.
const tabIndex = (element: HTMLElement) =>
  [...(element.parentElement?.querySelectorAll('[role="tab"]') ?? [])].indexOf(element)
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'offsetLeft', 'get').mockImplementation(function (this: HTMLElement) {
    return Math.max(0, tabIndex(this)) * 100
  })
  vi.spyOn(HTMLElement.prototype, 'offsetTop', 'get').mockReturnValue(4)
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(80)
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(32)
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  localStorage.clear()
  document.documentElement.className = ''
})
const chromium = () => vi.stubGlobal('navigator', { ...navigator, userAgentData: { brands: [{ brand: 'Chromium', version: '142' }] } })

const bar = (active: WorkspaceTab) => (
  <LiquidGlassProvider>
    <Tabs value={active}>
      <WorkspaceTabBar active={active} counts={{}} />
    </Tabs>
  </LiquidGlassProvider>
)
const thumb = (container: HTMLElement) => container.querySelector<HTMLElement>('[data-tab-thumb]')!

describe('WorkspaceTabBar glass', () => {
  it('draws one glass pill under the active tab, hidden from screen readers', () => {
    const { container } = render(bar('notes'))
    expect(thumb(container)).toHaveAttribute('aria-hidden', 'true')
    expect(thumb(container).style.transform).toBe('translate(100px, 4px)')
    expect(thumb(container).style.width).toBe('80px')
    expect(thumb(container).style.height).toBe('32px')
  })

  it('slides the pill to the newly chosen tab', () => {
    const { container, rerender } = render(bar('papers'))
    expect(thumb(container).style.transform).toBe('translate(0px, 4px)')
    rerender(bar('chat'))
    expect(thumb(container).style.transform).toBe('translate(200px, 4px)')
  })

  it('appears in place on first paint, then glides slowly to each new tab (650 ms, springy)', () => {
    const { container } = render(bar('papers'))
    expect(thumb(container)).toHaveAttribute('data-ready')
    expect(thumb(container).className).toContain('motion-safe:data-ready:transition-')
    expect(thumb(container).className).toContain('motion-safe:data-ready:duration-650')
  })

  it('is a clear lens over the labels where the browser bends light, using the Glass settings', () => {
    chromium()
    const { container } = render(bar('papers'))
    expect(thumb(container)).toHaveAttribute('data-lens')
    const lens = container.querySelector('filter#lg-tab-thumb')!
    expect(lens.getAttribute('primitiveUnits')).toBe('objectBoundingBox')
    expect(lens.querySelectorAll('feDisplacementMap')).toHaveLength(3)
  })

  it('stays an ordinary pill behind the labels in Safari and Firefox, or with Buttons switched off', () => {
    const { container } = render(bar('papers'))
    expect(thumb(container)).not.toHaveAttribute('data-lens')
    expect(container.querySelector('filter#lg-tab-thumb')).toBeNull()
  })

  it('lets the pill be the active tab\'s background, so the tab itself paints none', () => {
    render(bar('papers'))
    const tab = screen.getByRole('tab', { selected: true })
    expect(tab.className).toContain('data-active:bg-transparent')
    expect(tab.className).not.toContain('data-active:bg-background')
  })
})
