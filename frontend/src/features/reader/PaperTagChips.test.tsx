// @vitest-environment jsdom
import { render, screen, cleanup } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import { PaperTagChips } from './PaperTagChips'

const groups = (data: unknown) => vi.spyOn(queries, 'usePaperTagGroups').mockReturnValue({ data } as any)

afterEach(() => { cleanup(); vi.restoreAllMocks() })

test('tags are grouped per workspace and each chip links to that workspace filtered by the tag', () => {
  groups([
    { workspace_id: 'w1', workspace_name: 'Alpha', tags: ['rct', 'q1'] },
    { workspace_id: 'w2', workspace_name: 'Beta', tags: ['rct'] },
  ])
  render(<PaperTagChips paperId="p1" />)
  expect(screen.getByText('Alpha')).toBeTruthy()
  expect(screen.getByText('Beta')).toBeTruthy()
  const href = (name: string) => (screen.getByRole('link', { name }) as HTMLAnchorElement).getAttribute('href')
  expect(href('Show papers tagged rct in Alpha')).toBe('#/workspaces/w1?tags=rct')
  expect(href('Show papers tagged q1 in Alpha')).toBe('#/workspaces/w1?tags=q1')
  expect(href('Show papers tagged rct in Beta')).toBe('#/workspaces/w2?tags=rct')
})

test('a paper with no tags renders nothing', () => {
  groups([])
  const { container } = render(<PaperTagChips paperId="p1" />)
  expect(container.innerHTML).toBe('')
})
