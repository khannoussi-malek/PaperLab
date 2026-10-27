// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { act } from '@testing-library/react'
import { afterEach, beforeEach, expect, test } from 'vitest'
import type { PanelLimits } from '@/components/panelWidth'
import { StudioColumns, type StudioColumn } from './StudioColumns'

const limits = (storageKey: string): PanelLimits => ({ storageKey, defaultWidth: 200, minWidth: 100, maxShare: 0.4 })
const columns: StudioColumn[] = [
  { id: 'sections', label: 'Sections', content: <button>one</button>, limits: limits('t-sections') },
  { id: 'editor', label: 'Editor', content: <button>two</button> },
  { id: 'pdf', label: 'PDF', content: <button>three</button>, limits: limits('t-pdf') },
]
beforeEach(() => localStorage.clear())

test('collapsing shows a rail with an expand button, and the choice is remembered', () => {
  const { unmount } = render(<StudioColumns columns={columns} />)
  fireEvent.click(screen.getByRole('button', { name: 'Collapse Sections' }))
  expect(screen.getByText('one')).not.toBeVisible()
  expect(screen.getByRole('button', { name: 'Expand Sections' })).toHaveAttribute('aria-expanded', 'false')
  unmount()
  render(<StudioColumns columns={columns} />)
  expect(screen.getByText('one')).not.toBeVisible() // restored
  fireEvent.click(screen.getByRole('button', { name: 'Expand Sections' }))
  expect(screen.getByText('one')).toBeVisible()
  expect(JSON.parse(localStorage.getItem('paperlab-studio-collapsed')!)).toEqual([])
})

test('F6 and Shift+F6 cycle the expanded regions and skip collapsed ones', () => {
  render(<StudioColumns columns={columns} />)
  fireEvent.click(screen.getByRole('button', { name: 'Collapse Editor' }))
  const region = (n: string) => screen.getByRole('region', { name: n })
  region('Sections').focus()
  fireEvent.keyDown(document, { key: 'F6' })
  expect(region('PDF')).toHaveFocus()
  fireEvent.keyDown(document, { key: 'F6' })
  expect(region('Sections')).toHaveFocus()
  fireEvent.keyDown(document, { key: 'F6', shiftKey: true })
  expect(region('PDF')).toHaveFocus()
})

test('F6 is left alone once the studio is gone', () => {
  const { unmount } = render(<StudioColumns columns={columns} />)
  unmount()
  const e = new KeyboardEvent('keydown', { key: 'F6', cancelable: true })
  document.dispatchEvent(e)
  expect(e.defaultPrevented).toBe(false)
})

const wide = window.innerWidth
const setWidth = (w: number) => act(() => { Object.defineProperty(window, 'innerWidth', { value: w, configurable: true }); window.dispatchEvent(new Event('resize')) })
afterEach(() => setWidth(wide))
const shared: StudioColumn[] = [
  { id: 'editor', label: 'Editor', content: <button>ed</button> },
  { id: 'pdf', label: 'PDF', content: <button>pdf page</button>, limits: limits('t-pdf'), shareWith: 'papers' },
  { id: 'papers', label: 'Papers', content: <button>deck</button>, limits: limits('t-papers') },
]

test('wide enough, the PDF and the papers are two columns', () => {
  setWidth(1400)
  render(<StudioColumns columns={shared} />)
  expect(screen.getByRole('region', { name: 'PDF' })).toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'Papers' })).toBeInTheDocument()
  expect(screen.queryByRole('tab')).toBeNull()
})

test('under 1280 px they share one column as tabs, and the chosen tab is remembered', () => {
  setWidth(1000)
  const { unmount } = render(<StudioColumns columns={shared} />)
  expect(screen.getAllByRole('region')).toHaveLength(2)
  expect(screen.getByRole('tab', { name: 'PDF' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByText('deck')).not.toBeVisible()
  fireEvent.click(screen.getByRole('tab', { name: 'Papers' }))
  expect(screen.getByText('deck')).toBeVisible()
  expect(screen.getByText('pdf page')).not.toBeVisible()
  unmount()
  render(<StudioColumns columns={shared} />)
  expect(screen.getByRole('tab', { name: 'Papers' })).toHaveAttribute('aria-selected', 'true')
})

test('crossing the breakpoint while open switches layout', () => {
  setWidth(1400)
  render(<StudioColumns columns={shared} />)
  setWidth(900)
  expect(screen.getByRole('tab', { name: 'Papers' })).toBeInTheDocument()
})

test('reveal opens the Papers tab', () => {
  setWidth(1000)
  const { rerender } = render(<StudioColumns columns={shared} />)
  rerender(<StudioColumns columns={shared} reveal={{ id: 'papers', n: 1 }} />)
  expect(screen.getByText('deck')).toBeVisible()
})
