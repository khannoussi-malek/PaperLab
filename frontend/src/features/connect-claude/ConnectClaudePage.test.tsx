// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import { ConnectClaudePage } from './ConnectClaudePage'

const tools = Array.from({ length: 60 }, (_, i) => `tool_${i}`)
const mutate = vi.fn()

vi.mock('@/api/queries', () => ({
  useMcpSetup: () => ({ data: { folder: '/x' }, isError: false }),
  useCheckMcpServer: () => ({
    data: { ok: true, tools, detail: null },
    isPending: false,
    error: null,
    reset: vi.fn(),
    mutate,
  }),
}))
vi.mock('@/components/AppShell', () => ({ AppShell: ({ children }: { children: ReactNode }) => <div>{children}</div> }))
vi.mock('@/features/settings/desktop', () => ({ useDesktop: () => null }))

afterEach(cleanup)

test('says Claude can read, create and edit manuscripts, and that Claude Desktop asks before each call', () => {
  render(<ConnectClaudePage />)
  const can = screen.getByRole('region', { name: 'What Claude can do' })
  expect(can).toHaveTextContent("Read, create and edit your manuscripts' files, compile them")
  expect(can).toHaveTextContent('Claude Desktop asks you before each of these')
  expect(can).toHaveTextContent('restore in History')
  expect(screen.getByRole('region', { name: 'What Claude receives' })).toHaveTextContent('manuscript')
})

test('the check reports the real tool count', () => {
  render(<ConnectClaudePage />)
  fireEvent.click(screen.getByRole('button', { name: 'Check the server' }))
  expect(screen.getByRole('status')).toHaveTextContent('all 60 of its tools')
})
