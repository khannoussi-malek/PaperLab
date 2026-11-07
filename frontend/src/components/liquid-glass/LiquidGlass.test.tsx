// @vitest-environment jsdom
import { act, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LiquidGlassProvider } from './LiquidGlass'
import { useGlass } from './useGlass'
import { DEFAULT_GLASS, STORAGE_KEY } from './settings'

const chromium = () => vi.stubGlobal('navigator', { ...navigator, userAgentData: { brands: [{ brand: 'Chromium', version: '142' }] } })
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

// The probe hands the context out to the test after each render (act flushes the effect).
const probe = {} as { glass: ReturnType<typeof useGlass> }
function Probe() {
  const glass = useGlass()
  useEffect(() => {
    probe.glass = glass
  })
  return (
    <button type="button" data-slot="button" data-variant="outline">
      Find papers
    </button>
  )
}

beforeEach(() => {
  // jsdom lays nothing out; give every element a button's size.
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(120)
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(32)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  localStorage.clear()
  document.documentElement.className = ''
  document.documentElement.removeAttribute('style')
})

describe('LiquidGlassProvider', () => {
  it('applies the frost, saturation and opacity live, as CSS variables on the page', () => {
    render(<LiquidGlassProvider><Probe /></LiquidGlassProvider>)
    const root = document.documentElement.style
    expect(root.getPropertyValue('--lg-blur')).toBe('21.6px')
    expect(root.getPropertyValue('--lg-saturate')).toBe('105%')
    act(() => probe.glass.update({ blurAmount: 0.5, saturation: 200, opacity: 0.3 }))
    expect(root.getPropertyValue('--lg-blur')).toBe('20px')
    expect(root.getPropertyValue('--lg-saturate')).toBe('200%')
    expect(root.getPropertyValue('--lg-opacity')).toBe('0.3')
  })

  it('remembers changes in this browser, and Reset goes back to the defaults', () => {
    render(<LiquidGlassProvider><Probe /></LiquidGlassProvider>)
    act(() => probe.glass.update({ saturation: 220 }))
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!).saturation).toBe(220)
    act(() => probe.glass.reset())
    expect(probe.glass.settings).toEqual(DEFAULT_GLASS)
  })

  it('bends light only where the browser can and the switch is on', () => {
    chromium()
    render(<LiquidGlassProvider><Probe /></LiquidGlassProvider>)
    expect(document.documentElement).toHaveClass('liquid')
    act(() => probe.glass.update({ enabled: false }))
    expect(document.documentElement).not.toHaveClass('liquid')
  })

  it('keeps Safari and Firefox on frosted glass', () => {
    vi.stubGlobal('navigator', { ...navigator, userAgentData: undefined, userAgent: 'Mozilla/5.0 Gecko/20100101 Firefox/140.0' })
    render(<LiquidGlassProvider><Probe /></LiquidGlassProvider>)
    expect(document.documentElement).not.toHaveClass('liquid')
    expect(probe.glass.bendsLight).toBe(false)
  })

  it('gives a glass surface a lens of its own size, bending red, green and blue by the demo\'s formula', async () => {
    chromium()
    const { container } = render(<LiquidGlassProvider><Probe /></LiquidGlassProvider>)
    const button = screen.getByRole('button', { name: 'Find papers' })
    await waitFor(() => expect(button).toHaveAttribute('data-lg'))
    const id = button.style.getPropertyValue('--lg-lens').slice('url(#'.length, -1)
    expect(id).toMatch(/^lg-120x32/)
    const lens = await waitFor(() => {
      const found = container.querySelector(`filter[id="${id}"]`)
      expect(found).not.toBeNull()
      return found!
    })
    const scales = [...lens.querySelectorAll('feDisplacementMap')].map((map) => map.getAttribute('scale'))
    expect(scales).toEqual(['151', '160.82', '170.63'])
  })

  it('swaps the lens in place when Edge width moves, without taking the glass off (no flicker while dragging)', async () => {
    chromium()
    render(<LiquidGlassProvider><Probe /></LiquidGlassProvider>)
    const button = screen.getByRole('button', { name: 'Find papers' })
    await waitFor(() => expect(button.style.getPropertyValue('--lg-lens')).toContain('e8'))
    const seen: (string | null)[] = []
    const watch = new MutationObserver(() => seen.push(button.getAttribute('data-lg')))
    watch.observe(button, { attributes: true, attributeFilter: ['data-lg'] })
    act(() => probe.glass.update({ edgeWidth: 24 }))
    await waitFor(() => expect(button.style.getPropertyValue('--lg-lens')).toContain('e24'))
    watch.disconnect()
    expect(seen).not.toContain(null)
  })

  it('remembers changes once, outside React\'s state updaters', () => {
    const save = vi.spyOn(Storage.prototype, 'setItem')
    render(<LiquidGlassProvider><Probe /></LiquidGlassProvider>)
    save.mockClear()
    act(() => probe.glass.update({ saturation: 180 }))
    expect(save.mock.calls.filter(([key]) => key === STORAGE_KEY)).toHaveLength(1)
  })

  it('always gives the Settings preview its glass while glass is on, even with every area switched off', async () => {
    chromium()
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ areas: { floating: false, chrome: false, buttons: false, reader: false } }))
    render(
      <LiquidGlassProvider>
        <div data-glass-demo>Preview card</div>
      </LiquidGlassProvider>,
    )
    await waitFor(() => expect(screen.getByText('Preview card')).toHaveAttribute('data-lg'))
  })

  it('takes the glass off an area that is switched off', async () => {
    chromium()
    render(<LiquidGlassProvider><Probe /></LiquidGlassProvider>)
    const button = screen.getByRole('button', { name: 'Find papers' })
    await waitFor(() => expect(button).toHaveAttribute('data-lg'))
    act(() => probe.glass.update({ areas: { ...DEFAULT_GLASS.areas, buttons: false } }))
    await waitFor(() => expect(button).not.toHaveAttribute('data-lg'))
    expect(button.style.getPropertyValue('--lg-lens')).toBe('')
  })
})
