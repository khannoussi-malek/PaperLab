// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { graphHref } from '@/lib/route'
import { NavRail } from './NavRail'
import { forgetRailPill } from './useRailPill'

vi.mock('@/features/workspaces/WorkspaceSidebar', () => ({ WorkspaceSidebar: () => null }))

// jsdom lays nothing out: the rail starts at (0, 0); its links stack 36 px apart from y = 8, each 200 x 32 at x = 8.
const linkIndex = (element: Element) => [...(element.closest('nav')?.querySelectorAll('a') ?? [])].indexOf(element as HTMLAnchorElement)
beforeEach(() => {
  forgetRailPill()
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    if (this.tagName !== 'A') return DOMRect.fromRect({ x: 0, y: 0, width: 224, height: 800 })
    return DOMRect.fromRect({ x: 8, y: 8 + linkIndex(this) * 36, width: 200, height: 32 })
  })
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  // jsdom has no Web Animations; the tests that need it add a spy, removed here.
  delete (HTMLElement.prototype as Partial<HTMLElement>).animate
  window.location.hash = ''
})

const pill = () => document.querySelector<HTMLElement>('[data-rail-pill]')!

describe('the sidebar\'s glass pill', () => {
  it('sits on the current page\'s item, as decoration screen readers skip', () => {
    window.location.hash = '#/'
    render(<NavRail />)
    expect(pill()).toHaveAttribute('aria-hidden', 'true')
    expect(pill().style.transform).toBe('translate(8px, 8px)')
    expect(pill().style.width).toBe('200px')
    expect(pill().style.height).toBe('32px')
  })

  it('glides from the previous page\'s item to the new one, though every page draws its own sidebar', () => {
    const animate = vi.fn()
    HTMLElement.prototype.animate = animate
    window.location.hash = '#/'
    render(<NavRail />).unmount()
    expect(animate).not.toHaveBeenCalled()

    window.location.hash = graphHref
    render(<NavRail />)
    // It ends on Graph at once, and one transform animation (compositor-only, so a busy page can't stall it) runs
    // from where the last page left it, with the tabs' springy 650 ms.
    expect(pill().style.transform).toBe('translate(8px, 44px)')
    expect(animate).toHaveBeenCalledTimes(1)
    const [keyframes, timing] = animate.mock.calls[0]
    expect(keyframes).toEqual([{ transform: 'translate(8px, 8px)' }, { transform: 'translate(8px, 44px)' }])
    expect(timing).toMatchObject({ duration: 650, easing: 'cubic-bezier(0.34, 1.3, 0.64, 1)' })
  })

  it('jumps instead of gliding when the reader asks for reduced motion', () => {
    const animate = vi.fn()
    HTMLElement.prototype.animate = animate
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduce'), media: query, addEventListener() {}, removeEventListener() {} }))
    window.location.hash = '#/'
    render(<NavRail />).unmount()
    window.location.hash = graphHref
    render(<NavRail />)
    expect(pill().style.transform).toBe('translate(8px, 44px)')
    expect(animate).not.toHaveBeenCalled()
  })

  it('is the current item\'s only highlight there: the item itself paints no fill, but keeps its heavier weight', () => {
    window.location.hash = '#/'
    render(<NavRail />)
    const library = screen.getByRole('link', { name: 'Library' })
    expect(library.className).toContain('bg-transparent')
    expect(library.className).toContain('font-medium')
  })

  it('fades only (no slide by CSS), so the one glide is the animation above', () => {
    window.location.hash = '#/'
    render(<NavRail />)
    expect(pill().className).toContain('motion-safe:transition-opacity')
    expect(pill().className).not.toContain('transition-[transform')
  })
})
