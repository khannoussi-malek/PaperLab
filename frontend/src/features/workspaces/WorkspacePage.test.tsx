// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { WorkspacePage } from './WorkspacePage'

vi.mock('@/api/queries', () => ({ useWorkspace: () => ({ data: { name: 'W', paper_count: 1, note_count: 0 }, error: null }) }))
vi.mock('@/components/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <main>{children}</main>, shellTitle: () => null }))
vi.mock('./WorkspacePapers', () => ({
  WorkspacePapers: ({ onTagsChange }: { onTagsChange: (t: string[], m: 'any' | 'all') => void }) => (
    <button onClick={() => onTagsChange(['rct'], 'all')}>pick</button>
  ),
}))
vi.mock('@/features/workspace-search/ManualAcquisitionTab', () => ({ ManualAcquisitionTab: () => null }))
vi.mock('@/features/workspace-search/PrismaTab', () => ({ PrismaTab: () => null }))
vi.mock('@/features/workspace-search/ReadingQueueTab', () => ({ ReadingQueueTab: () => null }))
vi.mock('@/features/workspace-search/ScreeningTab', () => ({ ScreeningTab: () => null }))
vi.mock('@/features/workspace-search/SearchTab', () => ({ SearchTab: () => null }))
vi.mock('../evidence/EvidenceTab', () => ({ EvidenceTab: () => null }))
vi.mock('./WorkspaceChat', () => ({ WorkspaceChat: () => null }))
vi.mock('./WorkspaceNotes', () => ({ WorkspaceNotes: () => null }))
vi.mock('./ExportCitationsMenu', () => ({ ExportCitationsMenu: () => null }))

afterEach(cleanup)

test('a tag change keeps the active search run in the URL', () => {
  const replace = vi.fn()
  vi.stubGlobal('location', { ...window.location, replace })
  const run = '11111111-1111-4111-8111-111111111111'
  render(<WorkspacePage workspaceId="w1" tab="papers" runId={run} tags={[]} match="any" />)
  fireEvent.click(screen.getByText('pick'))
  expect(replace.mock.calls[0][0]).toContain(`run=${run}`)
})
