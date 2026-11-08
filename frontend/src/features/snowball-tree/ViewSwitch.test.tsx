// @vitest-environment jsdom
import { cleanup, fireEvent, render, renderHook, screen, act } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { useStoredView, ViewSwitch } from './ViewSwitch'

afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear() })

test('the options are Tree, Radial, Map, Outline and Tree is the default', () => {
  const { result } = renderHook(() => useStoredView('w1'))
  expect(result.current[0]).toBe('tree')
  render(<ViewSwitch value="tree" onChange={() => {}} />)
  expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['Tree', 'Radial', 'Map', 'Outline'])
  expect(screen.getByRole('button', { name: 'Tree' }).getAttribute('aria-pressed')).toBe('true')
})

test('the choice is remembered per workspace', () => {
  const first = renderHook(() => useStoredView('w1'))
  act(() => first.result.current[1]('map'))
  expect(localStorage.getItem('snowball-tree-view:w1')).toBe('map')
  expect(renderHook(() => useStoredView('w1')).result.current[0]).toBe('map')
  expect(renderHook(() => useStoredView('w2')).result.current[0]).toBe('tree')
})

test('falls back to Tree when localStorage throws', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
  const { result } = renderHook(() => useStoredView('w1'))
  expect(result.current[0]).toBe('tree')
  act(() => result.current[1]('outline'))
  expect(result.current[0]).toBe('outline')
})

test('clicking an option reports it', () => {
  const onChange = vi.fn()
  render(<ViewSwitch value="tree" onChange={onChange} />)
  fireEvent.click(screen.getByRole('button', { name: 'Radial' }))
  expect(onChange).toHaveBeenCalledWith('radial')
})
