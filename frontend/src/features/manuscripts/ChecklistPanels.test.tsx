// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { sileo } from 'sileo'
import { afterEach, beforeEach, expect, test, vi, type MockInstance } from 'vitest'
import { api, type ManuscriptDetail, type ReportingGuideline } from '@/api/client'
import { FinalStepsChecklist } from './FinalStepsChecklist'
import { GuidelineChecklist } from './GuidelineChecklist'

const ML: ReportingGuideline = {
  id: 'ml', label: 'ML reporting', applies_to: 'ml', source: 'test',
  items: [{ id: 'a', section: 'Data', text: 'Item A' }, { id: 'b', section: 'Data', text: 'Item B' }],
}
let patch: MockInstance<typeof api.updateManuscript>

function Both({ checklist }: { checklist: Record<string, unknown> }) {
  return (
    <>
      <FinalStepsChecklist manuscriptId="m1" checklist={checklist} />
      <GuidelineChecklist manuscriptId="m1" checklist={checklist} />
    </>
  )
}
function setup(checklist: Record<string, unknown>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const ui = (c: Record<string, unknown>) => <QueryClientProvider client={client}><Both checklist={c} /></QueryClientProvider>
  const view = render(ui(checklist))
  return { rerender: (c: Record<string, unknown>) => view.rerender(ui(c)) }
}

beforeEach(() => {
  vi.spyOn(api, 'listReportingGuidelines').mockResolvedValue([ML])
  patch = vi.spyOn(api, 'updateManuscript').mockReturnValue(new Promise(() => {})) // never settles
})
afterEach(() => vi.restoreAllMocks())

test('a final step then a guideline item, before the first save returns, both land in the second patch', async () => {
  setup({ guideline: 'ml' })
  fireEvent.click(screen.getByLabelText('Submit'))
  fireEvent.click(await screen.findByLabelText('Item A'))
  await waitFor(() => expect(patch).toHaveBeenCalledTimes(2))
  expect(patch).toHaveBeenLastCalledWith('m1', { checklist: { guideline: 'ml', Submit: true, 'ml:a': true } })
})

test('a guideline item then a final step also keeps both', async () => {
  setup({ guideline: 'ml' })
  fireEvent.click(await screen.findByLabelText('Item A'))
  fireEvent.click(screen.getByLabelText('Submit'))
  await waitFor(() => expect(patch).toHaveBeenCalledTimes(2))
  expect(patch).toHaveBeenLastCalledWith('m1', { checklist: { guideline: 'ml', 'ml:a': true, Submit: true } })
})

test('a late refetch of an older value does not drop a newer tick while a save is pending', async () => {
  const { rerender } = setup({ guideline: 'ml' })
  fireEvent.click(await screen.findByLabelText('Item A'))
  rerender({ guideline: 'ml' }) // stale prop (new object) lands while the save is pending
  fireEvent.click(screen.getByLabelText('Item B'))
  await waitFor(() => expect(patch).toHaveBeenCalledTimes(2))
  expect(patch).toHaveBeenLastCalledWith('m1', { checklist: { guideline: 'ml', 'ml:a': true, 'ml:b': true } })
})

test('a failed save reverts the box and shows a Sileo error', async () => {
  const toast = vi.spyOn(sileo, 'error').mockReturnValue('' as never)
  patch.mockRejectedValue(new Error('boom'))
  setup({ guideline: 'ml' })
  const box = await screen.findByLabelText('Item A')
  fireEvent.click(box)
  await waitFor(() => expect(toast).toHaveBeenCalled())
  await waitFor(() => expect(box.getAttribute('aria-checked')).toBe('false'))
})

test('a successful save keeps the box ticked', async () => {
  patch.mockResolvedValue({} as ManuscriptDetail)
  setup({ guideline: 'ml' })
  const box = await screen.findByLabelText('Item A')
  fireEvent.click(box)
  await waitFor(() => expect(patch).toHaveBeenCalled())
  expect(box.getAttribute('aria-checked')).toBe('true')
})
