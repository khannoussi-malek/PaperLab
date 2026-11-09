// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import { GraphPage } from './GraphPage'

const pending = { data: undefined, isError: false, isPending: true, failureCount: 0 }
vi.mock('@/api/queries', () => ({
  useLibraryGraph: () => pending,
  useWorkspaces: () => ({ data: [], isError: false }),
  useEmbeddingStatus: () => ({ data: undefined }),
  usePaperLinkMutations: () => {
    const idle = { isPending: false, reset: vi.fn(), mutate: vi.fn() }
    return { create: idle, rename: idle, remove: idle }
  },
}))
vi.mock('@/components/AppShell', () => ({
  AppShell: ({ children, status }: { children: ReactNode; status: ReactNode }) => (
    <div>
      <footer data-testid="status">{status}</footer>
      {children}
    </div>
  ),
}))

afterEach(cleanup)

test('while the graph loads, the page says so and the status shows no counts', () => {
  render(<GraphPage />)
  expect(screen.getByRole('status')).toHaveTextContent('Loading the graph…')
  expect(screen.getByTestId('status')).not.toHaveTextContent(/papers?,/)
})
