// @vitest-environment jsdom
import { render, screen, fireEvent } from '@testing-library/react'
import { expect, test, vi, afterEach } from 'vitest'
import { PrismaTab } from './PrismaTab'
import * as queries from '@/api/queries'
import type { PrismaExportOut } from '@/api/client'

const exportData: PrismaExportOut = {
  identified: 120,
  duplicates_removed: 20,
  stage1_screened: 100,
  stage1_excluded: 42,
  stage1_excluded_by_reason: { 'off topic': 42 },
  sought: 58,
  not_retrieved: 6,
  stage2_assessed: 52,
  stage2_excluded: 14,
  stage2_excluded_by_reason: { 'wrong population': 14 },
  included: 38,
  runs: [
    { id: 'run-1', query_text: 'transformer efficiency', filters_json: {}, started_at: '2026-09-24T00:00:00Z' },
    { id: 'run-2', query_text: 'llm evaluation', filters_json: {}, started_at: '2026-09-24T00:05:00Z' },
  ],
}

// Mirrors ScreeningTab.test.tsx's idiom: spy on the hook itself so the assertion can check the exact args
// usePrismaExport was re-invoked with, not just what the <select> displays.
function mockPrismaExport(data: PrismaExportOut) {
  return vi.spyOn(queries, 'usePrismaExport').mockReturnValue({ data } as ReturnType<typeof queries.usePrismaExport>)
}

afterEach(() => {
  vi.restoreAllMocks()
})

test('shows the full funnel with counts from usePrismaExport', () => {
  mockPrismaExport(exportData)
  render(<PrismaTab workspaceId="ws-1" />)

  expect(screen.getByText('Identified')).toBeInTheDocument()
  expect(screen.getByText('120')).toBeInTheDocument()
  expect(screen.getByText('Duplicates removed')).toBeInTheDocument()
  expect(screen.getByText('20')).toBeInTheDocument()
  expect(screen.getByText('Stage-1 screened')).toBeInTheDocument()
  expect(screen.getByText('100')).toBeInTheDocument()
  expect(screen.getByText('Stage-1 excluded')).toBeInTheDocument()
  expect(screen.getByText('42')).toBeInTheDocument()
  expect(screen.getByText('Reports sought')).toBeInTheDocument()
  expect(screen.getByText('58')).toBeInTheDocument()
  expect(screen.getByText('Not retrieved')).toBeInTheDocument()
  expect(screen.getByText('6')).toBeInTheDocument()
  expect(screen.getByText('Stage-2 assessed')).toBeInTheDocument()
  expect(screen.getByText('52')).toBeInTheDocument()
  expect(screen.getByText('Stage-2 excluded')).toBeInTheDocument()
  expect(screen.getByText('14')).toBeInTheDocument()
  expect(screen.getByText('Included')).toBeInTheDocument()
  expect(screen.getByText('38')).toBeInTheDocument()
})

test('toggles between combined and a specific run, re-querying usePrismaExport with the new runs value', () => {
  const spy = mockPrismaExport(exportData)
  render(<PrismaTab workspaceId="ws-1" />)

  expect(spy).toHaveBeenCalledWith('ws-1', 'all')
  const select = screen.getByRole('combobox', { name: 'Runs' })
  expect(screen.getByRole('option', { name: 'llm evaluation' })).toBeInTheDocument()

  fireEvent.change(select, { target: { value: 'run-2' } })

  expect(spy).toHaveBeenLastCalledWith('ws-1', 'run-2')
})
