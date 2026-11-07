// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react'
import { sileo } from 'sileo'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Notifications } from './Notifications'
import { ThemeProvider } from './theme-provider'

// Sileo reads the colour scheme and reduced motion and measures its toasts; jsdom has neither matchMedia nor
// ResizeObserver.
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }
const noMedia = (media: string) => ({ matches: false, media, addEventListener() {}, removeEventListener() {} })
beforeEach(() => vi.stubGlobal('matchMedia', noMedia))

afterEach(() => {
  vi.unstubAllGlobals()
  sileo.clear()
  localStorage.clear()
})

// The app mounts Notifications inside ThemeProvider (main.tsx); so do the tests.
const renderNotifications = () =>
  render(
    <ThemeProvider>
      <Notifications />
    </ThemeProvider>,
  )

describe('Notifications', () => {
  it('shows a passing notice in a polite live region, so screen readers hear it without losing focus', async () => {
    renderNotifications()
    act(() => void sileo.success({ title: 'DOI copied' }))
    const notice = await screen.findByText('DOI copied')
    expect(notice.closest('[aria-live="polite"]')).not.toBeNull()
  })

  it('leaves the toast in Sileo\'s own colours: PaperLab paints nothing on it', async () => {
    const { container } = renderNotifications()
    act(() => void sileo.success({ title: 'DOI copied' }))
    await screen.findByText('DOI copied')
    expect(container.querySelector('filter[id^="pl-"]')).toBeNull()
    expect(container.querySelector<HTMLElement>('[data-sileo-toast]')!.style.getPropertyValue('--pl-lens')).toBe('')
  })

  it('tells Sileo the app\'s theme, so its own colours stay readable in dark mode (no white text on a white pill)', async () => {
    localStorage.setItem('paperlab-theme', 'dark')
    renderNotifications()
    act(() => void sileo.success({ title: 'DOI copied' }))
    const notice = await screen.findByText('DOI copied')
    expect(notice.closest('[data-sileo-viewport]')).toHaveAttribute('data-theme', 'dark')
  })
})
