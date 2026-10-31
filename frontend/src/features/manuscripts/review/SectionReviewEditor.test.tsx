// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useState } from 'react'
import { EditorView } from '@codemirror/view'
import { afterEach, expect, test, vi } from 'vitest'
import { api, type SectionReview } from '@/api/client'
import { LatexEditor } from '../LatexEditor'
import { ReviewPanel } from './ReviewPanel'
import type { ReviewHandle } from './reviewMarks'
import { useReview } from './useReview'
import { useReviewInEditor } from './useReviewInEditor'
import { useSectionReview } from './useSectionReview'

Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as unknown as DOMRectList
afterEach(() => vi.restoreAllMocks())

const ONE = '\\section{Intro}\nSleep matters.\n', TWO = '\\section{Method}\nWe slept.\n'
const done = (id: string, hash: string, title: string): SectionReview => ({ id, file: 'main.tex', section_hash: hash, title, role: 'method', role_source: 'guessed', status: 'done', reason: null, findings: [{ kind: 'supported', point: `A point on ${title}`, refs: [{ kind: 'sentence', n: 1, hash: `s-${id}`, preview: 'Sleep matters.' }] }], dropped: 0, model: 'm', ai: true, created_at: '2026-10-31T00:00:00Z' })
const span = (hash: string, title: string, start: number, end: number) => ({ title, start, end, hash, words: 3, guess: null })

function Harness() {
  const [text, setText] = useState(ONE + TWO)
  const [handle, setHandle] = useState<ReviewHandle | null>(null)
  const review = useReview('m', 'main.tex')
  const section = useSectionReview('m', 'main.tex')
  const r = useReviewInEditor({ manuscriptId: 'm', workspaceId: 'w', review, text, handle, flush: async () => true, getBase: () => 'v1', sections: { file: 'main.tex', reviews: section.reviews } })
  return (
    <>
      <LatexEditor value={text} onChange={setText} errors={[]} onSave={() => {}} registerReview={setHandle} reviewLocate={(t) => api.locateSentences('m', t).then((x) => x.sentences)} />
      <ReviewPanel manuscriptId="m" review={review} stale={r.stale} onJump={r.jump} onCite={r.cite} onCheckAgain={() => {}}
        sections={{ reviews: section.reviews, stale: r.sectionStale, hasWorkspace: true, onCancel: () => {}, onReviewAgain: () => {} }} />
    </>
  )
}

test('editing a section turns its card stale while the other stays; a sentence chip selects the sentence', async () => {
  vi.spyOn(api, 'reviewState').mockResolvedValue({ run: null, items: [], dismissed: [] })
  vi.spyOn(api, 'sectionReviews').mockResolvedValue({ reviews: [done('a', 'h1', 'Intro'), done('b', 'h2', 'Method')] })
  const locate = vi.spyOn(api, 'locateSections').mockResolvedValue({ sections: [span('h1', 'Intro', 0, ONE.length), span('h2', 'Method', ONE.length, ONE.length + TWO.length)] })
  const at = ONE.indexOf('Sleep')
  vi.spyOn(api, 'locateSentences').mockResolvedValue({ sentences: [{ hash: 's-a', start: at, end: at + 'Sleep matters.'.length, keys: [] }] })
  const { container } = render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Harness /></QueryClientProvider>)
  await waitFor(() => expect(screen.getByRole('heading', { name: '“Intro”' })).toBeInTheDocument())
  await waitFor(() => expect(locate).toHaveBeenCalledWith('m', 'main.tex', ONE + TWO))
  expect(screen.queryByText('Changed since reviewed')).toBeNull()

  const view = EditorView.findFromDOM(container.querySelector<HTMLElement>('.cm-editor')!)!
  const chip = within(screen.getByRole('heading', { name: '“Intro”' }).closest('article')!).getByRole('button', { name: /S1 · Sleep matters/ })
  await act(async () => fireEvent.click(chip))
  await waitFor(() => expect(view.state.selection.main).toMatchObject({ from: at, to: at + 'Sleep matters.'.length }))

  locate.mockResolvedValue({ sections: [span('h1', 'Intro', 0, ONE.length), span('h2x', 'Method', ONE.length, ONE.length + TWO.length + 1)] })
  act(() => view.dispatch({ changes: { from: ONE.length + TWO.length - 1, insert: '!' }, userEvent: 'input' }))
  await waitFor(() => expect(screen.getByText('Changed since reviewed')).toBeInTheDocument(), { timeout: 3000 })
  const changed = screen.getByText('Changed since reviewed').closest('div')!
  expect(within(changed).getByText('“Method”')).toBeInTheDocument()
  expect(within(changed).queryByText('“Intro”')).toBeNull()
  expect(screen.getByRole('heading', { name: '“Intro”' })).toBeInTheDocument()
  expect(screen.getByText('A point on Intro')).toBeInTheDocument()
})
