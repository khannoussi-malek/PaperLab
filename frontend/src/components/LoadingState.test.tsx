// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TabSkeleton } from '@/features/workspaces/TabStates'
import { LoadingState } from './LoadingState'

describe('LoadingState', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('adds no extra line at 0 s', () => {
    render(<LoadingState />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading…')
    expect(screen.queryByText('Still loading…')).toBeNull()
  })

  it('says "Still loading…" after 3 s', () => {
    render(<LoadingState />)
    act(() => void vi.advanceTimersByTime(3000))
    expect(screen.getByText('Still loading…')).toBeInTheDocument()
  })

  it('says the app is being retried when a request failed', () => {
    render(<LoadingState failureCount={1} />)
    expect(screen.getByText("The app didn't answer; trying again…")).toBeInTheDocument()
    expect(screen.queryByText('Still loading…')).toBeNull()
  })

  it('works inside TabSkeleton too', () => {
    render(<TabSkeleton label="Loading notes" failureCount={2} />)
    expect(screen.getByText("The app didn't answer; trying again…")).toBeInTheDocument()
  })

  it('leaves no timer behind after unmount', () => {
    const { unmount } = render(<LoadingState />)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})
