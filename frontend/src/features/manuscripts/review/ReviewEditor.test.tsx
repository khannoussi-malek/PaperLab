// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { EditorView } from '@codemirror/view'
import { afterEach, expect, test, vi } from 'vitest'
import { api, type CheckItem } from '@/api/client'
import { LatexEditor } from '../LatexEditor'
import { ReviewPanel } from './ReviewPanel'
import type { ReviewHandle } from './reviewMarks'
import { useReview } from './useReview'
import { useReviewInEditor } from './useReviewInEditor'

Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as unknown as DOMRectList
afterEach(() => vi.restoreAllMocks())

const item = (hash: string, sentence: string, verdict: string): CheckItem => ({ id: hash, kind: 'cited', file: 'main.tex', sentence_hash: hash, sentence, ord: 0, cite_key: 'k', paper_id: 'p', paper_title: 't', status: 'done', verdict, reason: null, quote: null, page: null, chunk_id: null, output_id: null, model: 'm', ai: true }) as CheckItem
const A = 'Alpha is true.', B = 'Beta is false.'

function Harness() {
  const [text, setText] = useState(`${A} ${B}`)
  const [handle, setHandle] = useState<ReviewHandle | null>(null)
  const review = useReview('m', 'main.tex')
  const r = useReviewInEditor({ manuscriptId: 'm', workspaceId: 'w', review, text, handle, flush: async () => true, getBase: () => 'v1' })
  return (
    <>
      <LatexEditor value={text} onChange={setText} errors={[]} onSave={() => {}} registerReview={setHandle} reviewLocate={(t) => api.locateSentences('m', t).then((x) => x.sentences)} />
      <ReviewPanel manuscriptId="m" review={review} stale={r.stale} onJump={r.jump} onCite={r.cite} onCheckAgain={() => void r.check()} />
    </>
  )
}

test('marks show with the AI badge; an edited sentence loses its mark and moves to "Changed since checked"', async () => {
  vi.spyOn(api, 'reviewState').mockResolvedValue({ run: { id: 'r', status: 'done', total: 2, done: 2, reason: null, uncited_skipped: 0 }, items: [item('h1', A, 'supported'), item('h2', B, 'not_supported')], dismissed: [] } as never)
  const locate = vi.spyOn(api, 'locateSentences').mockResolvedValue({ sentences: [{ hash: 'h1', start: 0, end: 14, keys: [] }, { hash: 'h2', start: 15, end: 29, keys: [] }] })
  const { container } = render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Harness /></QueryClientProvider>)
  await waitFor(() => expect(container.querySelectorAll('.cm-review-badge')).toHaveLength(2))
  expect(container.querySelector('.cm-review-badge')).toHaveTextContent('Supports')
  expect(screen.queryByText('Changed since checked')).toBeNull()

  locate.mockResolvedValue({ sentences: [{ hash: 'h1', start: 0, end: 14, keys: [] }, { hash: 'zz', start: 15, end: 28, keys: [] }] })
  const view = EditorView.findFromDOM(container.querySelector<HTMLElement>('.cm-editor')!)!
  act(() => view.dispatch({ changes: { from: 27, to: 28, insert: '' }, userEvent: 'input' }))
  await waitFor(() => expect(screen.getByText('Changed since checked')).toBeInTheDocument(), { timeout: 3000 })
  expect(container.querySelectorAll('.cm-review-badge')).toHaveLength(1)
  expect(container.querySelector('.cm-review-badge')).toHaveTextContent('Supports')
})
