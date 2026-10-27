// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import type { Lens, Section } from '@/api/client'
import { LensPanel } from './LensPanel'
import type { LensReader } from './useLensReader'

vi.mock('./queries', () => ({
  usePaperBriefs: () => ({ data: [] }),
  useInvalidateBriefs: () => vi.fn(),
  useSetSectionRole: () => ({ error: new Error('Could not save the role'), isPending: false, mutate: vi.fn() }),
}))

it('a rejected role save shows its error above the sections', () => {
  const lens = { id: 'full', label: 'Full paper', chunk_ids: [], positional_fallback: false, missing_roles: [] } as unknown as Lens
  const reader = { lens, sections: [] as Section[], sectionsQuery: { error: null } } as unknown as LensReader
  render(
    <QueryClientProvider client={new QueryClient()}>
      <LensPanel paperId="p1" reader={reader} hasPdf />
    </QueryClientProvider>,
  )
  expect(screen.getByRole('alert')).toHaveTextContent('Could not save the role')
})
