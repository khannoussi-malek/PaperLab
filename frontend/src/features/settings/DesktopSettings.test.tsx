// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { DesktopSettings } from './DesktopSettings'

const on = async () => true
const set = async () => {}
const base = { getKeepRunning: on, setKeepRunning: set, getUpdatesEnabled: on, setUpdatesEnabled: set }

afterEach(() => {
  delete (globalThis as { paperlabDesktop?: unknown }).paperlabDesktop
})

describe('DesktopSettings', () => {
  it('offers the floating paper switch when the desktop app has it (macOS)', async () => {
    ;(globalThis as { paperlabDesktop?: unknown }).paperlabDesktop = { ...base, getCaptureFloat: on, setCaptureFloat: set }
    render(<DesktopSettings />)
    expect(await screen.findByText('Floating paper')).toBeInTheDocument()
  })

  it('leaves it out when the app has no floating paper', async () => {
    ;(globalThis as { paperlabDesktop?: unknown }).paperlabDesktop = base
    render(<DesktopSettings />)
    expect(await screen.findByText('Check for updates on launch')).toBeInTheDocument()
    expect(screen.queryByText('Floating paper')).toBeNull()
  })
})
