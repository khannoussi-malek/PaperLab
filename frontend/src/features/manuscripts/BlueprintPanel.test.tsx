// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '@/api/client'
import { BlueprintPanel } from './BlueprintPanel'

const T = '2026-11-10T00:00:00Z'
const file = (path: string) => ({ path, size: 1, updated_at: T })

function renderPanel({ files }: { files: { path: string }[] }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <BlueprintPanel manuscriptId="m1" files={files.map((f) => file(f.path))} />
    </QueryClientProvider>,
  )
}

function mockFile(path: string, text: string) {
  return vi.spyOn(api, 'getManuscriptFile').mockResolvedValue({ path, size: text.length, updated_at: T, text })
}

afterEach(() => vi.restoreAllMocks())

test('renders nothing when the manuscript has no blueprint.json', () => {
  renderPanel({ files: [{ path: 'main.tex' }] })
  expect(screen.queryByRole('region', { name: 'Paper plan' })).toBeNull()
})

test('shows the plan read-only', async () => {
  mockFile('blueprint.json', '{"title":"Fast retrieval","contributions":["A graph"],"notation":[{"symbol":"\\\\alpha","meaning":"weight"}],"target_words":{"method":[600,1500]}}')
  renderPanel({ files: [{ path: 'main.tex' }, { path: 'blueprint.json' }] })
  expect(await screen.findByText('Fast retrieval')).toBeInTheDocument()
  expect(screen.getByText('A graph')).toBeInTheDocument()
  expect(screen.getByText('weight')).toBeInTheDocument()
  expect(screen.getByText(/600 to 1500/)).toBeInTheDocument()
  expect(screen.queryByRole('textbox')).toBeNull() // read-only
})

test('an unreadable file is one muted line', async () => {
  mockFile('blueprint.json', 'not json')
  renderPanel({ files: [{ path: 'blueprint.json' }] })
  expect(await screen.findByText("blueprint.json can't be read. Open it in All files to fix it.")).toBeInTheDocument()
})
