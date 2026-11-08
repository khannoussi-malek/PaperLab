// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '@/api/client'
import { BranchControl } from './BranchControl'

function setup(branch: { state: string; directions: string[]; reason: string | null } | null = null) {
  const setBranch = vi.spyOn(api, 'setBranch').mockResolvedValue({} as any)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <BranchControl workspaceId="w1" target={{ hit_id: 'h1' }} branch={branch} />
    </QueryClientProvider>,
  )
  return setBranch
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })

test('shows the three buttons and no options while undecided', () => {
  setup()
  for (const name of ['Go further', 'Stop here', 'Undecided']) expect(screen.getByRole('button', { name })).toBeTruthy()
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(screen.queryByLabelText('Reason')).toBeNull()
})

test('Go further shows both direction boxes, checked, and saves both directions', async () => {
  const setBranch = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Go further' }))
  const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[]
  expect(boxes).toHaveLength(2)
  expect(boxes.every((b) => b.checked)).toBe(true)
  expect(screen.queryByLabelText('Reason')).toBeNull()
  await waitFor(() => expect(setBranch).toHaveBeenCalledWith('w1', {
    hit_id: 'h1', state: 'go_further', directions: ['cites', 'cited_by'], reason: null,
  }))
})

test('unchecking one direction saves the other', async () => {
  const setBranch = setup({ state: 'go_further', directions: ['cites', 'cited_by'], reason: null })
  fireEvent.click(screen.getByRole('checkbox', { name: 'Papers citing it' }))
  await waitFor(() => expect(setBranch).toHaveBeenCalledWith('w1', {
    hit_id: 'h1', state: 'go_further', directions: ['cites'], reason: null,
  }))
})

test('Stop here shows the reason field and saves the reason', async () => {
  const setBranch = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Stop here' }))
  expect(screen.queryByRole('checkbox')).toBeNull()
  const reason = screen.getByLabelText('Reason')
  fireEvent.change(reason, { target: { value: 'too general' } })
  fireEvent.blur(reason)
  await waitFor(() => expect(setBranch).toHaveBeenLastCalledWith('w1', {
    hit_id: 'h1', state: 'stopped', directions: [], reason: 'too general',
  }))
})

test('Undecided clears the decision', async () => {
  const setBranch = setup({ state: 'stopped', directions: [], reason: 'x' })
  fireEvent.click(screen.getByRole('button', { name: 'Undecided' }))
  await waitFor(() => expect(setBranch).toHaveBeenCalledWith('w1', { hit_id: 'h1', state: null, directions: [], reason: null }))
})

test('a failed save shows the message and puts the buttons back', async () => {
  const setBranch = setup()
  setBranch.mockRejectedValue(new Error('Server said no'))
  fireEvent.click(screen.getByRole('button', { name: 'Go further' }))
  expect(await screen.findByText('Server said no')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Undecided' }).getAttribute('aria-pressed')).toBe('true')
  expect(screen.queryByRole('checkbox')).toBeNull()
})

test('the direction labels are Its references and Papers citing it', () => {
  setup({ state: 'go_further', directions: ['cites', 'cited_by'], reason: null })
  expect(screen.getByLabelText('Its references')).toBeTruthy()
  expect(screen.getByLabelText('Papers citing it')).toBeTruthy()
})
