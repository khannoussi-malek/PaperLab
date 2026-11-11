// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi, type MockInstance } from 'vitest'
import { api, type ManuscriptDetail, type ReportingGuideline } from '@/api/client'
import { GuidelineChecklist } from './GuidelineChecklist'

const ML: ReportingGuideline = {
  id: 'ml',
  label: 'ML reporting',
  applies_to: 'machine learning',
  source: 'test',
  items: [
    { id: 'data.source', section: 'Data', text: 'Name the data source' },
    { id: 'data.size', section: 'Data', text: 'Report the dataset size' },
    ...Array.from({ length: 16 }, (_, i) => ({ id: `misc.${i}`, section: 'Model', text: `ML item ${i}` })),
  ],
}
const PRISMA: ReportingGuideline = {
  id: 'prisma2020',
  label: 'PRISMA 2020',
  applies_to: 'systematic reviews',
  source: 'test',
  items: Array.from({ length: 27 }, (_, i) => ({ id: `item.${i}`, section: 'Methods', text: `PRISMA item ${i}` })),
}

let patch: MockInstance<typeof api.updateManuscript>

function renderPanel(props: { checklist: Record<string, unknown> }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <GuidelineChecklist manuscriptId="m1" checklist={props.checklist} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.spyOn(api, 'listReportingGuidelines').mockResolvedValue([ML, PRISMA])
  patch = vi.spyOn(api, 'updateManuscript').mockResolvedValue({} as ManuscriptDetail)
})

afterEach(() => {
  vi.restoreAllMocks()
})

test('shows its items unticked and a count', async () => {
  renderPanel({ checklist: { guideline: 'ml' } })
  expect(await screen.findByText('0 of 18 ticked')).toBeInTheDocument()
  expect(screen.getAllByRole('checkbox').every((c) => c.getAttribute('aria-checked') === 'false')).toBe(true)
})

test('ticking sends the merged checklist, keeping final steps', async () => {
  renderPanel({ checklist: { guideline: 'ml', Submit: true } })
  fireEvent.click((await screen.findAllByRole('checkbox'))[0])
  await waitFor(() => expect(patch).toHaveBeenCalledWith('m1', { checklist: { guideline: 'ml', Submit: true, 'ml:data.source': true } }))
})

test('choosing a guideline sets only the guideline key', async () => {
  renderPanel({ checklist: { Submit: true } })
  await screen.findByRole('option', { name: 'PRISMA 2020' })
  fireEvent.change(await screen.findByLabelText('Reporting guideline'), { target: { value: 'prisma2020' } })
  await waitFor(() => expect(patch).toHaveBeenCalledWith('m1', { checklist: { Submit: true, guideline: 'prisma2020' } }))
})

test('two quick ticks both land (the patch is built from the panel\'s latest ref)', async () => {
  renderPanel({ checklist: { guideline: 'ml' } })
  const boxes = await screen.findAllByRole('checkbox')
  fireEvent.click(boxes[0])
  fireEvent.click(boxes[1]) // the prop is stale; the panel's latest ref holds the first tick
  await waitFor(() => expect(patch).toHaveBeenLastCalledWith('m1', { checklist: { guideline: 'ml', 'ml:data.source': true, 'ml:data.size': true } }))
})

test('an incomplete list disables nothing', async () => {
  renderPanel({ checklist: { guideline: 'ml' } })
  await screen.findByText('0 of 18 ticked')
  expect(document.querySelectorAll('[disabled]').length).toBe(0)
})

test('while loading or failed, only the picker shows and nothing crashes', async () => {
  vi.spyOn(api, 'listReportingGuidelines').mockRejectedValue(new Error('x'))
  renderPanel({ checklist: { guideline: 'ml' } })
  expect(screen.getByLabelText('Reporting guideline')).toBeInTheDocument()
  expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
})
