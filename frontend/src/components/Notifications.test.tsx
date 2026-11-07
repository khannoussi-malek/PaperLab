// @vitest-environment jsdom
import { act, render, screen, waitFor } from '@testing-library/react'
import { sileo } from 'sileo'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Notifications } from './Notifications'

// Sileo reads the colour scheme and reduced motion and measures its toasts; jsdom has neither matchMedia nor
// ResizeObserver.
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }
// No canvas in jsdom either: the lens map comes back empty, which leaves the filter inert (and keeps jsdom quiet).
HTMLCanvasElement.prototype.getContext = (() => null) as typeof HTMLCanvasElement.prototype.getContext
const noMedia = (media: string) => ({ matches: false, media, addEventListener() {}, removeEventListener() {} })
beforeEach(() => vi.stubGlobal('matchMedia', noMedia))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.documentElement.classList.remove('liquid')
  sileo.clear()
})

describe('Notifications', () => {
  it('shows a passing notice in a polite live region, so screen readers hear it without losing focus', async () => {
    render(<Notifications />)
    act(() => void sileo.success({ title: 'DOI copied' }))
    const notice = await screen.findByText('DOI copied')
    expect(notice.closest('[aria-live="polite"]')).not.toBeNull()
  })

  it('gives each toast its own lens, shaped from its outline, and points the toast\'s backdrop at it', async () => {
    // jsdom lays nothing out; give the toast Sileo's real width so its shape can be read.
    vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(350)
    vi.stubGlobal('navigator', { ...navigator, userAgentData: { brands: [{ brand: 'Chromium', version: '142' }] } })
    const { container } = render(<Notifications />)
    act(() => void sileo.success({ title: 'DOI copied' }))
    await screen.findByText('DOI copied')
    const toast = container.querySelector<HTMLElement>('[data-sileo-toast]')!
    await waitFor(() => expect(toast.style.getPropertyValue('--pl-lens')).toMatch(/^url\(#pl-lens-\d+\)$/))
    const id = toast.style.getPropertyValue('--pl-lens').slice('url(#'.length, -1)
    const lens = await waitFor(() => {
      const found = container.querySelector(`filter[id="${id}"]`)
      expect(found).not.toBeNull()
      return found
    })
    // Three bends (red, green, blue) for the colour split, then a frosted centre under a crisp rim.
    expect(lens!.querySelectorAll('feDisplacementMap')).toHaveLength(3)
    expect(lens!.querySelector('feGaussianBlur')).not.toBeNull()
  })

  it('draws the glass surface filter markup: a specular highlight from the top left and a bright rim', () => {
    const { container } = render(<Notifications />)
    const surface = container.querySelector('filter#pl-glass-surface')
    expect(surface).not.toBeNull()
    expect(surface!.querySelector('feSpecularLighting feDistantLight')).not.toBeNull()
    expect(surface!.querySelector('feMorphology[operator="erode"]')).not.toBeNull()
  })

  it('turns the bending on only where the browser can do it', () => {
    vi.stubGlobal('navigator', { ...navigator, userAgentData: { brands: [{ brand: 'Chromium', version: '142' }] } })
    const { unmount } = render(<Notifications />)
    expect(document.documentElement).toHaveClass('liquid')
    unmount()
    expect(document.documentElement).not.toHaveClass('liquid')
  })

  it('leaves Safari and Firefox on frosted glass', () => {
    vi.stubGlobal('navigator', { ...navigator, userAgentData: undefined, userAgent: 'Mozilla/5.0 Gecko/20100101 Firefox/140.0' })
    render(<Notifications />)
    expect(document.documentElement).not.toHaveClass('liquid')
  })
})
