// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type Paper } from '@/api/client'
import { PaperMenu } from './PaperMenu'

const paper = { id: 'p1', title: 'Alpha', workspace_ids: [], reading_pass: 0, triage: null } as unknown as Paper
afterEach(() => vi.restoreAllMocks())

async function open(workspaceId?: string) {
  vi.spyOn(api, 'listWorkspaces').mockResolvedValue([])
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PaperMenu paper={paper} workspaceId={workspaceId} onMembershipChange={vi.fn()} onReadingChange={vi.fn()} />
    </QueryClientProvider>,
  )
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Paper actions' }), { button: 0, ctrlKey: false })
  await screen.findByRole('menuitem', { name: 'Reading' })
}

it('offers both snowball items inside a workspace only', async () => {
  await open('w1')
  expect(screen.getByRole('menuitem', { name: 'Find citing & cited papers' })).toBeTruthy()
  expect(screen.getByRole('menuitem', { name: 'Navigate from here' })).toBeTruthy()
})

it('hides them outside a workspace', async () => {
  await open()
  expect(screen.queryByRole('menuitem', { name: 'Find citing & cited papers' })).toBeNull()
  expect(screen.queryByRole('menuitem', { name: 'Navigate from here' })).toBeNull()
})

it('Find citing & cited papers snowballs from only this paper', async () => {
  const run = vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 2, skipped_seeds: [], errors: {} } as never)
  await open('w1')
  fireEvent.click(screen.getByRole('menuitem', { name: 'Find citing & cited papers' }))
  await waitFor(() => expect(run).toHaveBeenCalledWith('w1', { seed_paper_ids: ['p1'], backward: true, forward: true }))
})

it('Navigate from here opens the tree tab with navPaper', async () => {
  window.location.hash = ''
  await open('w1')
  fireEvent.click(screen.getByRole('menuitem', { name: 'Navigate from here' }))
  expect(window.location.hash).toContain('tab=tree')
  expect(window.location.hash).toContain('navPaper=p1')
})
