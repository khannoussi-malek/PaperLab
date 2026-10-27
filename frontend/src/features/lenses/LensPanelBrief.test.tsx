// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api, type Lens, type Section } from '@/api/client'
import { LensPanel } from './LensPanel'
import type { LensReader } from './useLensReader'

let briefs: { data?: unknown[]; isPending: boolean; error: Error | null; refetch: () => void }
vi.mock('./queries', () => ({
  useSetSectionRole: () => ({ error: null, isPending: false, mutate: vi.fn() }),
  usePaperBriefs: () => briefs,
  useInvalidateBriefs: () => vi.fn(),
}))

const client = new QueryClient()
const tree = (id: string) => {
  const label = { full: 'Full paper', key_ideas: 'Key ideas', method: 'How they did it' }[id]
  const lens = { id, label, chunk_ids: ['c1'], positional_fallback: false, missing_roles: [] } as unknown as Lens
  const reader = { lens, sections: [] as Section[], sectionsQuery: { error: null } } as unknown as LensReader
  return <QueryClientProvider client={client}><LensPanel paperId="p1" reader={reader} hasPdf /></QueryClientProvider>
}
const panel = (id: string) => render(tree(id))

beforeEach(() => {
  briefs = { data: [], isPending: false, error: null, refetch: vi.fn() }
})

describe('LensPanel brief card', () => {
  it('is hidden for the full paper', () => {
    panel('full')
    expect(screen.queryByRole('region', { name: /brief/ })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Generate brief' })).toBeNull()
  })

  it('is shown for Key ideas', () => {
    panel('key_ideas')
    expect(screen.getByRole('button', { name: 'Generate brief' })).toBeInTheDocument()
  })

  it('offers no Generate while the saved briefs load', () => {
    briefs = { isPending: true, error: null, refetch: vi.fn() }
    panel('key_ideas')
    expect(screen.queryByRole('button', { name: 'Generate brief' })).toBeNull()
  })

  it('shows a load error with Retry, not Generate, when the briefs fail to load', () => {
    briefs = { isPending: false, error: new Error('briefs down'), refetch: vi.fn() }
    panel('key_ideas')
    expect(screen.getByRole('alert')).toHaveTextContent('briefs down')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Generate brief' })).toBeNull()
  })

  it('a brief refused for want of a model links to Settings and keeps Generate, also after switching lens and back', async () => {
    vi.spyOn(api, 'generateBrief').mockResolvedValue(Response.json({ detail: 'no_model' }, { status: 409 }))
    const { rerender } = panel('key_ideas')
    fireEvent.click(screen.getByRole('button', { name: 'Generate brief' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Add a model in Settings to write briefs.')
    expect(screen.getByRole('link', { name: 'Open settings' })).toHaveAttribute('href', '#/settings/models')
    expect(screen.getByRole('button', { name: 'Generate brief' })).toBeInTheDocument()

    rerender(tree('method'))
    expect(screen.getByRole('button', { name: 'Generate brief' })).toBeInTheDocument()
    rerender(tree('key_ideas'))
    expect(screen.getByRole('button', { name: 'Generate brief' })).toBeInTheDocument()
  })
})
