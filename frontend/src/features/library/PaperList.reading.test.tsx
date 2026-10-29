// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type Paper } from '@/api/client'

vi.mock('../graph/hands/HandsMode', () => ({ default: () => null }))
vi.mock('./PaperPreview', () => ({ PaperPreview: () => <aside>preview</aside> }))
import { PaperList } from './PaperList'

const paper = { id: 'p1', title: 'Alpha cells', authors: [], year: null, status: 'ready', has_pdf: true, reading_pass: 0, triage: null } as unknown as Paper
afterEach(() => vi.restoreAllMocks())

it('a reading change from the row menu is sent with the library source', async () => {
  const put = vi.spyOn(api, 'setReading').mockResolvedValue(paper)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PaperList papers={[paper]} />
    </QueryClientProvider>
  )
  const trigger = screen.getByRole('button', { name: 'Paper actions' })
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false })
  fireEvent.keyDown(await screen.findByRole('menuitem', { name: 'Reading' }), { key: 'ArrowRight' })
  fireEvent.click(await screen.findByRole('menuitemradio', { name: 'Later' }))
  await waitFor(() => expect(put).toHaveBeenCalledWith('p1', { triage: 'later' }, 'library'))
})
