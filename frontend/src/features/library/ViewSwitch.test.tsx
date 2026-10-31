// @vitest-environment jsdom
import { act, fireEvent, render, renderHook, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ViewSwitch, usePaperView } from './ViewSwitch'

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); sessionStorage.clear() })

it('renders List, Deck and Triage with aria-pressed on the current one', () => {
  const onChange = vi.fn()
  render(<ViewSwitch view="triage" onChange={onChange} />)
  expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['List', 'Deck', 'Triage'])
  expect(screen.getByRole('button', { name: 'Triage' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: 'List' })).toHaveAttribute('aria-pressed', 'false')
  fireEvent.click(screen.getByRole('button', { name: 'Deck' }))
  expect(onChange).toHaveBeenCalledWith('deck')
})

it('never restores triage: a stored triage, junk, null or a throwing store reopen on the list; deck is restored', () => {
  localStorage.setItem('k', 'triage')
  expect(renderHook(() => usePaperView('k')).result.current[0]).toBe('list')
  localStorage.setItem('k', 'deck')
  expect(renderHook(() => usePaperView('k')).result.current[0]).toBe('deck')
  localStorage.setItem('k', 'garbage')
  expect(renderHook(() => usePaperView('k')).result.current[0]).toBe('list')
  localStorage.removeItem('k')
  expect(renderHook(() => usePaperView('k')).result.current[0]).toBe('list')
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
  expect(renderHook(() => usePaperView('k')).result.current[0]).toBe('list')
})

it('leaving triage ends that scope session', () => {
  sessionStorage.setItem('paperlab-triage-session:library', 'abc')
  const { result } = renderHook(() => usePaperView('k', 'library'))
  act(() => result.current[1]('triage'))
  act(() => result.current[1]('deck'))
  expect(sessionStorage.getItem('paperlab-triage-session:library')).toBeNull()
})
