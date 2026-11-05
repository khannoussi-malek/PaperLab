// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '@/api/client'
import { HybridSearchSwitch } from './HybridSearchSwitch'

afterEach(() => vi.restoreAllMocks())

const show = (enabled: boolean) => render(
  <QueryClientProvider client={new QueryClient()}><HybridSearchSwitch enabled={enabled} /></QueryClientProvider>,
)
const box = () => screen.getByRole('checkbox', { name: 'Also match exact words when searching across papers' })

test('shows its state and says what it does and what it costs', () => {
  show(false)
  expect(box()).not.toBeChecked()
  expect(box()).toHaveAccessibleDescription(/rare names and numbers/)
  expect(box()).toHaveAccessibleDescription(/Chat about a workspace or a long paper always does this/)
  expect(box()).toHaveAccessibleDescription(/long passage/)
  expect(box()).toHaveAccessibleDescription(/seconds/)
})

test('turning it on saves the choice', async () => {
  const save = vi.spyOn(api, 'setHybridSearch').mockResolvedValue({ hybrid_search: true })
  show(false)
  fireEvent.click(box())
  await waitFor(() => expect(save).toHaveBeenCalledWith(true))
})

test('a failed save says why', async () => {
  vi.spyOn(api, 'setHybridSearch').mockRejectedValue(new Error('The server is down'))
  show(true)
  expect(box()).toBeChecked()
  fireEvent.click(box())
  expect(await screen.findByText('The server is down')).toBeInTheDocument()
})
