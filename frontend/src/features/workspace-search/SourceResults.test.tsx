// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'
import type { SearchRun } from '@/api/client'
import { SourceResults } from './SourceResults'

afterEach(cleanup)

const run = (fields: Partial<SearchRun>) => fields as SearchRun

test('a partial run says so and gives each source its state, counts and reason', () => {
  render(
    <SourceResults
      run={run({
        outcome: 'partial',
        source_results: [
          { source: 'arxiv', state: 'paused', raw_count: 200, new_hits: 150, reason: 'Stopped at 200 results for this pass; Continue fetches more.' },
          { source: 'semantic_scholar', state: 'gave_up', raw_count: 0, new_hits: 0, reason: 'Gave up after 6 failed attempts: HTTP 429 from api.semanticscholar.org' },
        ],
      })}
    />,
  )
  expect(screen.getByText(/Partial search/)).toBeTruthy()
  const rows = screen.getAllByRole('listitem').map((row) => row.textContent)
  expect(rows[0]).toContain('arXiv: paused · 200 results, 150 new')
  expect(rows[1]).toContain('Semantic Scholar: gave up · 0 results, 0 new · Gave up after 6 failed attempts')
})

test('a complete run says every source finished', () => {
  render(<SourceResults run={run({ outcome: 'complete', source_results: [{ source: 'arxiv', state: 'complete', raw_count: 3, new_hits: 3 }] })} />)
  expect(screen.getByText('Every source finished.')).toBeTruthy()
  expect(screen.queryByText(/Partial search/)).toBeNull()
})

test('a warning shows while the run is still running', () => {
  render(<SourceResults run={run({ outcome: 'running', warnings: [{ source: 'semantic_scholar', message: 'Semantic Scholar refuses most searches without an API key.' }] })} />)
  expect(screen.getByRole('status').textContent).toContain('without an API key')
})

test('a run with nothing to report shows nothing', () => {
  const { container } = render(<SourceResults run={run({ outcome: 'complete' })} />)
  expect(container.innerHTML).toBe('')
})
