// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { api, type Chart, type ChartSpec } from '@/api/client'

vi.mock('@/features/charts/ChartView', () => ({ ChartView: ({ spec }: { spec: ChartSpec }) => <div>drawn {spec.type}</div> }))
import { ChatChart } from './ChatChart'

const spec = { type: 'bar', series: [] } as unknown as ChartSpec

test('a chart answer is drawn and can be saved as a chart', async () => {
  const create = vi.spyOn(api, 'createChart').mockResolvedValue({ id: 'c9' } as Chart)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ChatChart spec={spec} title="F1 by system" />
    </QueryClientProvider>,
  )
  expect(screen.getByText('drawn bar')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Save chart' }))
  await waitFor(() => expect(create).toHaveBeenCalledWith('F1 by system', spec))
  expect(await screen.findByRole('link', { name: 'Open saved chart' })).toHaveAttribute('href', '#/charts/c9')
})
