// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, ApiError, type Workspace } from '@/api/client'
import { MakeEditableBanner, READ_ONLY_BANNER } from './MakeEditable'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const workspace = (read_only: boolean) => ({ id: 'w1', name: 'Sepsis', read_only }) as unknown as Workspace

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

test('an editable workspace shows no banner and no button', () => {
  wrap(<MakeEditableBanner workspace={workspace(false)} />)
  expect(screen.queryByText(READ_ONLY_BANNER)).toBeNull()
  expect(screen.queryByRole('button', { name: 'Make it editable' })).toBeNull()
})

test('a read-only workspace shows the banner and the Make it editable button', () => {
  wrap(<MakeEditableBanner workspace={workspace(true)} />)
  expect(screen.getByText('Imported read-only. Make it editable to change its papers, tags, criteria or searches.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Make it editable' })).toBeTruthy()
})

test('the button asks first; confirming calls the API for this workspace', async () => {
  const spy = vi.spyOn(api, 'makeWorkspaceEditable').mockResolvedValue(workspace(false))
  wrap(<MakeEditableBanner workspace={workspace(true)} />)
  fireEvent.click(screen.getByRole('button', { name: 'Make it editable' }))
  expect(screen.getByText('Make this workspace editable?')).toBeTruthy()
  expect(screen.getByText('It stays editable.')).toBeTruthy()
  expect(spy).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Make editable' }))
  await waitFor(() => expect(spy).toHaveBeenCalledWith('w1'))
})

test('cancel closes the dialog and changes nothing', () => {
  const spy = vi.spyOn(api, 'makeWorkspaceEditable').mockResolvedValue(workspace(false))
  wrap(<MakeEditableBanner workspace={workspace(true)} />)
  fireEvent.click(screen.getByRole('button', { name: 'Make it editable' }))
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(spy).not.toHaveBeenCalled()
  expect(screen.queryByText('Make this workspace editable?')).toBeNull()
})

test('a refused make-editable shows the words, not the code', async () => {
  vi.spyOn(api, 'makeWorkspaceEditable').mockRejectedValue(new ApiError('workspace_read_only', 409, { code: 'workspace_read_only' }))
  wrap(<MakeEditableBanner workspace={workspace(true)} />)
  fireEvent.click(screen.getByRole('button', { name: 'Make it editable' }))
  fireEvent.click(screen.getByRole('button', { name: 'Make editable' }))
  expect(await screen.findByRole('alert')).toBeTruthy()
})
