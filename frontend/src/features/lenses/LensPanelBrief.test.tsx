// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Lens, Section } from '@/api/client'
import { LensPanel } from './LensPanel'
import type { LensReader } from './useLensReader'

let briefs: { data?: unknown[]; isPending: boolean; error: Error | null; refetch: () => void }
vi.mock('./queries', () => ({
  useSetSectionRole: () => ({ error: null, isPending: false, mutate: vi.fn() }),
  usePaperBriefs: () => briefs,
  useInvalidateBriefs: () => vi.fn(),
}))

const panel = (id: string) => {
  const lens = { id, label: id === 'full' ? 'Full paper' : 'Key ideas', chunk_ids: ['c1'], positional_fallback: false, missing_roles: [] } as unknown as Lens
  const reader = { lens, sections: [] as Section[], sectionsQuery: { error: null } } as unknown as LensReader
  render(<QueryClientProvider client={new QueryClient()}><LensPanel paperId="p1" reader={reader} hasPdf /></QueryClientProvider>)
}

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
})
