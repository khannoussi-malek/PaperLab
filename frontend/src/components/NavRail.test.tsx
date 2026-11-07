// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { chartsHref, graphHref } from '@/lib/route'
import { NavRail } from './NavRail'
import { forgetRailPill } from './useRailPill'

vi.mock('@/features/workspaces/WorkspaceSidebar', () => ({ WorkspaceSidebar: () => null }))
// The page change in progress, as withViewTransition reports it; none unless a test sets one.
const transition = vi.hoisted(() => ({ current: null as { ready: Promise<void> } | null }))
vi.mock('@/components/motion', async (original) => ({
  ...(await original<typeof import('@/components/motion')>()),
  currentViewTransition: () => transition.current,
}))
const glideStub = () => ({ pause: vi.fn(), play: vi.fn(), cancel: vi.fn() })
/** A stand-in for Element.animate (jsdom has none) that records its calls and returns a controllable glide. */
const stubAnimate = (glide = glideStub()) => {
  const animate = vi.fn((...args: Parameters<HTMLElement['animate']>) => {
    void args
    return glide as unknown as Animation
  })
  HTMLElement.prototype.animate = animate
  return animate
}

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
  transition.current = null
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
    const animate = stubAnimate()
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

  it('during a page change, waits for the new page to show before gliding, so the glide isn\'t spent behind it', async () => {
    const glide = glideStub()
    stubAnimate(glide)
    let show!: () => void
    transition.current = { ready: new Promise<void>((resolve) => (show = resolve)) }
    window.location.hash = '#/'
    render(<NavRail />).unmount()
    window.location.hash = graphHref
    render(<NavRail />)
    expect(glide.pause).toHaveBeenCalled()
    expect(glide.play).not.toHaveBeenCalled()
    await act(async () => show())
    expect(glide.play).toHaveBeenCalled()
  })

  it('jumps instead of gliding when the reader asks for reduced motion', () => {
    const animate = stubAnimate()
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduce'), media: query, addEventListener() {}, removeEventListener() {} }))
    window.location.hash = '#/'
    render(<NavRail />).unmount()
    window.location.hash = graphHref
    render(<NavRail />)
    expect(pill().style.transform).toBe('translate(8px, 44px)')
    expect(animate).not.toHaveBeenCalled()
  })

  it('in the one persistent sidebar, a second click mid-glide carries on from where the pill is drawn, not from a jump', () => {
    const animate = stubAnimate()
    window.location.hash = '#/'
    render(<NavRail />)
    const go = (hash: string) =>
      act(() => {
        const oldURL = window.location.href
        window.location.hash = hash
        window.dispatchEvent(new HashChangeEvent('hashchange', { oldURL, newURL: window.location.href }))
      })

    go(graphHref)
    expect(animate).toHaveBeenLastCalledWith([{ transform: 'translate(8px, 8px)' }, { transform: 'translate(8px, 44px)' }], expect.anything())

    // Mid-glide, the pill is drawn at y = 20 on its way to Graph; Charts is clicked.
    const realStyle = window.getComputedStyle
    vi.spyOn(window, 'getComputedStyle').mockImplementation((element) =>
      element === pill() ? ({ transform: 'matrix(1, 0, 0, 1, 8, 20)' } as CSSStyleDeclaration) : realStyle(element),
    )
    go(chartsHref)
    expect(animate).toHaveBeenLastCalledWith([{ transform: 'translate(8px, 20px)' }, { transform: 'translate(8px, 80px)' }], expect.anything())
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
