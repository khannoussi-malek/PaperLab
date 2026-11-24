// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AnswerCheck as Check, AnswerCheckSentence } from '@/entities'
import { api, ApiError } from '@/services/api'
import { AnswerCheck } from './AnswerCheck'

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

const s = (index: number, over: Partial<AnswerCheckSentence> = {}): AnswerCheckSentence => ({
  index,
  text: `Sentence ${index}.`,
  labels: ['C1'],
  state: 'done',
  verdict: 'supported',
  reason: 'The passage says so.',
  quote: 'the passage says so',
  quote_label: 'C1',
  confidence: 'high',
  shortened: false,
  ...over,
})

const check = (over: Partial<Check> = {}): Check => ({
  id: 'check-1',
  state: 'done',
  model: 'qwen3:8b',
  connection_name: 'Ollama',
  created_at: '2026-11-21T10:00:00Z',
  summary: '1 supported · 1 not supported',
  limit_hit: false,
  sentences: [s(0), s(1, { verdict: 'not_supported', reason: 'It says 28.4, not 32.4.', quote: null, quote_label: null })],
  ...over,
})

const conflict = (code: string, body: Record<string, unknown> = {}) => new ApiError(code, 409, { detail: code, ...body })

function setup(known = false) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AnswerCheck outputId="out-1" known={known} />
    </QueryClientProvider>,
  )
}

describe('AnswerCheck', () => {
  it('shows the button and fetches nothing when the answer was never checked', async () => {
    const get = vi.spyOn(api, 'answerCheck').mockResolvedValue(null)
    setup()
    expect(await screen.findByRole('button', { name: 'Check this answer' })).toBeInTheDocument()
    expect(get).not.toHaveBeenCalled()
  })

  it('shows an earlier finished check without a click', async () => {
    vi.spyOn(api, 'answerCheck').mockResolvedValue(check())
    setup(true)
    expect(await screen.findByText(/Checked by qwen3:8b/)).toBeInTheDocument()
    expect(screen.getByText(/1 supported · 1 not supported/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Check again' })).toBeInTheDocument()
    expect(screen.getAllByText('AI check')).toHaveLength(2)
    expect(screen.getByText('Not supported')).toBeInTheDocument()
    expect(screen.getByText('✗')).toBeInTheDocument()
    expect(screen.getByText('It says 28.4, not 32.4.')).toBeInTheDocument()
    expect(screen.getByText(/can miss a figure moved to the wrong group/)).toBeInTheDocument()
  })

  it('starts a check and polls until it is done', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const running = check({ state: 'running', summary: '', sentences: [s(0), s(1, { state: 'pending', verdict: null })] })
    const get = vi.spyOn(api, 'answerCheck').mockResolvedValueOnce(running).mockResolvedValue(check())
    const start = vi.spyOn(api, 'startAnswerCheck').mockResolvedValue(running)
    setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Check this answer' }))
    await waitFor(() => expect(start).toHaveBeenCalledWith('out-1', false))
    expect(await screen.findByText('Checking 1 of 2 sentences…')).toBeInTheDocument()
    await act(async () => { await vi.advanceTimersByTimeAsync(2100) })
    await waitFor(() => expect(screen.getByText(/Checked by qwen3:8b/)).toBeInTheDocument())
    expect(get).toHaveBeenCalled()
  })

  it('asks before sending to a cloud model, then sends with the yes', async () => {
    vi.spyOn(api, 'answerCheck').mockResolvedValue(null)
    const start = vi.spyOn(api, 'startAnswerCheck')
      .mockRejectedValueOnce(conflict('remote_model_needs_confirm', { host: 'api.example.com' }))
      .mockResolvedValue(check({ state: 'running', sentences: [s(0, { state: 'pending', verdict: null })] }))
    setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Check this answer' }))
    expect((await screen.findAllByText(/answer and the passages it cites will be sent to api.example.com/)).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(start).toHaveBeenLastCalledWith('out-1', true))
  })

  it('says why an old answer cannot be checked', async () => {
    vi.spyOn(api, 'answerCheck').mockResolvedValue(null)
    vi.spyOn(api, 'startAnswerCheck').mockRejectedValue(conflict('answer_not_checkable'))
    setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Check this answer' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      "This answer was saved before PaperLab kept copies of its passages, so it can't be checked.",
    )
  })

  it('marks a sentence judged on a shortened passage and a low-confidence verdict', async () => {
    vi.spyOn(api, 'answerCheck').mockResolvedValue(
      check({ sentences: [s(0, { shortened: true, confidence: 'low', quote: null })] }),
    )
    setup(true)
    expect(await screen.findByText(/judged on a shortened passage/)).toBeInTheDocument()
    expect(screen.getByText(/low confidence/)).toBeInTheDocument()
  })
})
