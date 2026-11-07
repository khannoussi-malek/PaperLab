// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LiquidGlassProvider } from '@/components/liquid-glass/LiquidGlass'
import { STORAGE_KEY } from '@/components/liquid-glass/settings'
import { GlassSettings } from './GlassSettings'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

const renderSection = () =>
  render(
    <LiquidGlassProvider>
      <GlassSettings />
    </LiquidGlassProvider>,
  )
const stored = () => JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  document.documentElement.className = ''
})

describe('Settings → Glass', () => {
  it('has the demo\'s four sliders, under the demo\'s names, plus edge width and opacity, at the owner\'s defaults', () => {
    renderSection()
    expect(screen.getByRole('slider', { name: 'Displacement scale' })).toHaveValue('80')
    expect(screen.getByRole('slider', { name: 'Blur amount' })).toHaveValue('0.0375')
    expect(screen.getByRole('slider', { name: 'Saturation' })).toHaveValue('105')
    expect(screen.getByRole('slider', { name: 'Chromatic aberration' })).toHaveValue('0')
    expect(screen.getByRole('slider', { name: 'Edge width' })).toHaveValue('14')
    expect(screen.getByRole('slider', { name: 'Opacity' })).toHaveValue('0.35')
  })

  it('points to the demo, so values can be tried there first', () => {
    renderSection()
    expect(screen.getByRole('link', { name: /liquid-glass-react demo/ })).toHaveAttribute('href', 'https://liquid-glass.maxrovensky.com')
  })

  it('applies a slider at once, shows its value, and remembers it', () => {
    renderSection()
    fireEvent.change(screen.getByRole('slider', { name: 'Saturation' }), { target: { value: '200' } })
    expect(screen.getByText('200%')).toBeInTheDocument()
    expect(stored().saturation).toBe(200)
    expect(document.documentElement.style.getPropertyValue('--lg-saturate')).toBe('200%')
  })

  it('switches glass off for one area', () => {
    renderSection()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Buttons and the workspace tab pill' }))
    expect(stored().areas.buttons).toBe(false)
  })

  it('switches it all off, which greys the sliders out', () => {
    renderSection()
    fireEvent.click(screen.getByRole('switch', { name: 'Liquid glass' }))
    expect(stored().enabled).toBe(false)
    expect(screen.getByRole('slider', { name: 'Saturation' })).toBeDisabled()
  })

  it('resets to the defaults', () => {
    renderSection()
    fireEvent.change(screen.getByRole('slider', { name: 'Opacity' }), { target: { value: '0.2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Reset to defaults' }))
    expect(screen.getByRole('slider', { name: 'Opacity' })).toHaveValue('0.35')
  })

  it('says when this browser can only frost', () => {
    vi.stubGlobal('navigator', { ...navigator, userAgentData: undefined, userAgent: 'Mozilla/5.0 Gecko/20100101 Firefox/140.0' })
    renderSection()
    expect(screen.getByText(/can't bend light/)).toBeInTheDocument()
  })

  describe('the live preview', () => {
    const preview = () => within(screen.getByRole('region', { name: 'Glass preview' }))

    it('sits beside the sliders on a wide screen and above them on a narrow one, pinned while they scroll either way', () => {
      renderSection()
      const column = screen.getByRole('region', { name: 'Glass preview' }).parentElement!
      expect(column.className).toMatch(/(^| )sticky( |$)/)
      expect(column.className).toContain('max-lg:order-first')
      expect(column.parentElement!.className).toContain('lg:grid-cols-')
    })

    it('shows a glass card over a busy, colourful background, which the sliders change live', () => {
      renderSection()
      const card = preview().getByRole('group', { name: /Glass sample/ })
      expect(card).toHaveAttribute('data-glass-demo')
    })

    it('lets the card be moved over the background with the arrow keys (or dragged)', () => {
      renderSection()
      const card = preview().getByRole('group', { name: /Glass sample/ })
      const before = card.style.transform
      fireEvent.keyDown(card, { key: 'ArrowRight' })
      fireEvent.keyDown(card, { key: 'ArrowDown' })
      expect(card.style.transform).not.toBe(before)
      expect(card.style.transform).toBe('translate(36px, 36px)')
    })

    it('has the real tab bar, with its gliding pill, to try', () => {
      renderSection()
      expect(preview().getByRole('tab', { name: 'Papers' })).toHaveAttribute('aria-selected', 'true')
      fireEvent.mouseDown(preview().getByRole('tab', { name: 'Notes' }), { button: 0 })
      expect(preview().getByRole('tab', { name: 'Notes' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByRole('region', { name: 'Glass preview' }).querySelector('[data-tab-thumb]')).not.toBeNull()
    })

    it('has a menu whose highlight glides to the item under the pointer', () => {
      renderSection()
      const item = preview().getByText('Rename')
      fireEvent.pointerEnter(item)
      expect(item).toHaveAttribute('data-highlighted')
      expect(screen.getByRole('region', { name: 'Glass preview' }).querySelector('[data-menu-glide]')).not.toBeNull()
    })

    it('has the three button styles', () => {
      renderSection()
      for (const name of ['Primary', 'Outline', 'Secondary']) expect(preview().getByRole('button', { name })).toBeInTheDocument()
    })
  })
})
