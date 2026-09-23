// @vitest-environment jsdom
import { render, screen, fireEvent } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { SearchControls } from './SearchControls'

test('typing a query and clicking Start calls onStart with the query', () => {
  const onStart = vi.fn()
  render(<SearchControls onStart={onStart} isRunning={false} />)

  fireEvent.change(screen.getByLabelText('Search query'), { target: { value: 'code review LLM' } })
  fireEvent.click(screen.getByRole('button', { name: 'Start' }))

  expect(onStart).toHaveBeenCalledWith({
    query: 'code review LLM',
    filters: {},
    sources: expect.any(Array),
    query_overrides: {},
  })
})

test('shows Stop instead of Start while a run is in progress', () => {
  render(<SearchControls onStart={vi.fn()} isRunning={true} />)
  expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()
})

test('disables Start until a query is typed', () => {
  render(<SearchControls onStart={vi.fn()} isRunning={false} />)
  expect(screen.getByRole('button', { name: 'Start' })).toBeDisabled()
})
