// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, test } from 'vitest'
import { PaperSourceRow } from './PaperSourceRow'
import type { PaperSource } from '@/api/client'

function renderRow(source: PaperSource, hasEmail: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ul>
        <PaperSourceRow source={source} hasEmail={hasEmail} />
      </ul>
    </QueryClientProvider>,
  )
}

const source = (overrides: Partial<PaperSource>): PaperSource => ({
  id: 'crossref', name: 'Crossref', enabled: true, has_key: null, key_hint: null, ...overrides,
})

test('OpenAlex shows the "May cost money" badge and its price line', () => {
  renderRow(source({ id: 'openalex', name: 'OpenAlex', has_key: false }), true)
  expect(screen.getByText('May cost money')).toBeInTheDocument()
  expect(screen.getByText(/Free up to \$0.10 of use a day/)).toBeInTheDocument()
})

test('Crossref shows neither the badge nor a prerequisite hint', () => {
  renderRow(source({}), true)
  expect(screen.queryByText('May cost money')).not.toBeInTheDocument()
  expect(screen.queryByText(/Add a contact email/)).not.toBeInTheDocument()
})

test('Unpaywall without a contact email shows the prerequisite hint', () => {
  renderRow(source({ id: 'unpaywall', name: 'Unpaywall' }), false)
  expect(screen.getByText('Add a contact email to use Unpaywall.')).toBeInTheDocument()
})

test('Unpaywall with a contact email shows no hint', () => {
  renderRow(source({ id: 'unpaywall', name: 'Unpaywall' }), true)
  expect(screen.queryByText(/Add a contact email/)).not.toBeInTheDocument()
})
