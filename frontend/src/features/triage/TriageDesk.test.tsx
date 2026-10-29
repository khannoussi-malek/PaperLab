// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, expect, it, vi } from 'vitest'
import type { Paper } from '@/api/client'
import { TriageDesk } from './TriageDesk'

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  Element.prototype.scrollIntoView = () => {}
  Element.prototype.hasPointerCapture = () => false
})
afterEach(() => { cleanup(); sessionStorage.clear(); localStorage.clear() })

const mk = (id: string, title: string, extra: Partial<Paper> = {}) =>
  ({ id, title, authors: [], year: null, status: 'ready', has_pdf: true, reading_pass: null, triage: null, created_at: `2026-01-0${id}T00:00:00Z`, ...extra }) as unknown as Paper
const base = [mk('1', 'Old one'), mk('2', 'Middle'), mk('3', 'New one')]

function setup(papers: Paper[] = base, onExit = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TriageDesk papers={papers} library={papers} scope="library" sourceLabel="your library" filterKey="" onExit={onExit} onShowKept={vi.fn()} />
    </QueryClientProvider>,
  )
  return onExit
}

it('is a focused group with the bar counts and the card title', () => {
  setup()
  const desk = screen.getByRole('group', { name: 'Triage' })
  expect(desk).toHaveAttribute('aria-roledescription', 'triage desk')
  expect(desk).toHaveFocus()
  expect(screen.getByText(/Triage · your library · 3 left of 3/)).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Old one' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Exit (Esc)' })).toBeInTheDocument()
})

it('counts papers still being read in', () => {
  setup([...base, mk('4', 'Busy', { status: 'embedding' as Paper['status'] })])
  expect(screen.getByText(/1 paper is still being read in/)).toBeInTheDocument()
})

it('Include decided adds the decided papers to the stack', () => {
  setup([mk('1', 'Done', { triage: 'keep' }), mk('2', 'Open')])
  expect(screen.getByText(/1 left of 1/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('switch', { name: 'Include decided papers' }))
  expect(screen.getByText(/2 left of 2/)).toBeInTheDocument()
})

it('order change persists and re-sorts the rest of the stack', () => {
  setup()
  fireEvent.keyDown(screen.getByRole('combobox', { name: 'Order' }), { key: 'ArrowDown' })
  fireEvent.click(screen.getByRole('option', { name: 'Title A to Z' }))
  expect(localStorage.getItem('paperlab-triage-order:library')).toBe('title')
})

it('opens with its saved order', () => {
  localStorage.setItem('paperlab-triage-order:library', 'newest')
  setup()
  expect(screen.getByRole('heading', { name: 'New one' })).toBeInTheDocument()
})

it('says so when everything is already decided, with two ways forward', () => {
  const onExit = setup([mk('1', 'Done', { triage: 'keep' })])
  expect(screen.getByText('Nothing to triage here. Every paper in this view already has a decision.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Include decided papers' }))
  expect(screen.getByRole('heading', { name: 'Done' })).toBeInTheDocument()
  expect(onExit).not.toHaveBeenCalled()
})

it('Back to the list leaves', () => {
  const onExit = setup([mk('1', 'Done', { triage: 'keep' })])
  fireEvent.click(screen.getByRole('button', { name: 'Back to the list' }))
  expect(onExit).toHaveBeenCalledTimes(1)
})

it('Esc leaves once and removes the session', () => {
  const onExit = setup()
  expect(sessionStorage.getItem('paperlab-triage-session:library')).not.toBeNull()
  fireEvent.keyDown(screen.getByRole('group', { name: 'Triage' }), { key: 'Escape' })
  expect(onExit).toHaveBeenCalledTimes(1)
  expect(sessionStorage.getItem('paperlab-triage-session:library')).toBeNull()
})
