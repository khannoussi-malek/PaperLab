// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ClaudeActivity } from './ClaudeActivity'

type Row = { at: string; tool: string; arguments: string; outcome: string; duration_ms: number; is_write: boolean }

const mocks = vi.hoisted(() => ({
  activity: { data: [] as Row[] | undefined, isError: false, error: null as Error | null, refetch: vi.fn() },
  settings: { data: { writes_enabled: true } as { writes_enabled: boolean } | undefined, isError: false, error: null },
  setWrites: vi.fn(),
  clear: vi.fn(),
}))

vi.mock('@/api/queries', () => ({
  useMcpActivity: () => mocks.activity,
  useMcpSettings: () => mocks.settings,
  useSetMcpWrites: () => ({ mutate: mocks.setWrites, isPending: false, error: null }),
  useClearMcpActivity: () => ({ mutate: mocks.clear, isPending: false, error: null }),
}))

const search: Row = {
  at: '2026-11-13T09:00:00Z',
  tool: 'search_library',
  arguments: '{"query":"tidal volume"}',
  outcome: 'ok',
  duration_ms: 12,
  is_write: false,
}
const add: Row = {
  at: '2026-11-13T09:05:00Z',
  tool: 'add_paper',
  arguments: '{"identifier":"10.1/x"}',
  outcome: 'writes_disabled',
  duration_ms: 1,
  is_write: true,
}
const WHEN = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' })

beforeEach(() => {
  mocks.activity.data = [search, add]
  mocks.settings.data = { writes_enabled: true }
  vi.clearAllMocks()
})
afterEach(cleanup)

test('lists each call with its time, tool, arguments and result under the four column names', () => {
  render(<ClaudeActivity />)
  const region = screen.getByRole('region', { name: 'What Claude did' })
  for (const column of ['When', 'Tool', 'Asked with', 'Result']) {
    expect(within(region).getByRole('columnheader', { name: column })).toBeInTheDocument()
  }
  const row = screen.getByText('search_library').closest('tr') as HTMLElement
  expect(within(row).getByText(WHEN.format(new Date(search.at)))).toBeInTheDocument()
  expect(within(row).getByText('{"query":"tidal volume"}')).toBeInTheDocument()
  expect(within(row).getByText('ok')).toBeInTheDocument()
})

test('a write call carries a Change badge and a read call does not', () => {
  render(<ClaudeActivity />)
  expect(screen.getByText('add_paper').closest('tr')).toHaveTextContent('Change')
  expect(screen.getByText('search_library').closest('tr')).not.toHaveTextContent('Change')
})

test('an empty log says so', () => {
  mocks.activity.data = []
  render(<ClaudeActivity />)
  expect(screen.getByText('No tool calls yet.')).toBeInTheDocument()
})

test('clear asks in a dialog first and never uses window.confirm', () => {
  const nativeConfirm = vi.fn(() => true)
  vi.stubGlobal('confirm', nativeConfirm)
  render(<ClaudeActivity />)

  fireEvent.click(screen.getByRole('button', { name: 'Clear the list' }))
  expect(mocks.clear).not.toHaveBeenCalled()

  const dialog = screen.getByRole('alertdialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Clear' }))
  expect(mocks.clear).toHaveBeenCalledTimes(1)
  expect(nativeConfirm).not.toHaveBeenCalled()
  vi.unstubAllGlobals()
})

test('the switch shows the saved setting, saves the new one and explains what off means', () => {
  render(<ClaudeActivity />)
  const toggle = screen.getByRole('switch', { name: 'Let Claude change your library' })
  expect(toggle).toBeChecked()
  expect(
    screen.getByText("Off: Claude can still search and read, but can't add, tag, write or delete anything."),
  ).toBeInTheDocument()

  fireEvent.click(toggle)
  expect(mocks.setWrites).toHaveBeenCalledWith(false)
})

test('the switch reads off when the owner has turned changes off', () => {
  mocks.settings.data = { writes_enabled: false }
  render(<ClaudeActivity />)
  expect(screen.getByRole('switch', { name: 'Let Claude change your library' })).not.toBeChecked()
})
