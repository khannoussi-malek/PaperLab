// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { PdfTabs } from './PdfTabs'

afterEach(cleanup)

it('shows Paper and PDF as tabs, marks the selected one and selects on click', () => {
  const onTab = vi.fn()
  render(<PdfTabs tab="paper" onTab={onTab} />)
  expect(screen.getByRole('tab', { name: 'Paper' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tab', { name: 'PDF' })).toHaveAttribute('aria-selected', 'false')
  fireEvent.click(screen.getByRole('tab', { name: 'PDF' }))
  expect(onTab).toHaveBeenCalledWith('pdf')
})

it('arrows on a focused tab change tab and stop there; the other tab is the one reached', () => {
  const onTab = vi.fn()
  const outer = vi.fn()
  render(<div onKeyDown={outer}><PdfTabs tab="paper" onTab={onTab} /></div>)
  fireEvent.keyDown(screen.getByRole('tab', { name: 'Paper' }), { key: 'ArrowRight' })
  expect(onTab).toHaveBeenLastCalledWith('pdf')
  fireEvent.keyDown(screen.getByRole('tab', { name: 'Paper' }), { key: 'ArrowLeft' })
  expect(onTab).toHaveBeenLastCalledWith('pdf')
  expect(outer).not.toHaveBeenCalled()
})
