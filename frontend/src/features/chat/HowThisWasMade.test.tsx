// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, type AnswerProvenance } from '@/api/client'
import { HowThisWasMade } from './HowThisWasMade'

afterEach(() => vi.restoreAllMocks())

const PAPER = '1f0e7570-3249-4d59-aa5c-8f9a03c2b70a'
const CREATED = '2026-11-12T09:30:00Z'

const view = (over: Partial<AnswerProvenance> = {}): AnswerProvenance => ({
  model: 'qwen3:14b',
  connection_name: 'Home server',
  prompt_version: 3,
  skill_label: null,
  created_at: CREATED,
  out_of_date: false,
  passages: [],
  ...over,
})

function setup(props: { outputId: string } | { noteId: string }) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <HowThisWasMade {...props} />
    </QueryClientProvider>,
  )
  return screen.getByRole('button', { name: 'How this was made' })
}

describe('HowThisWasMade', () => {
  it('is closed by default and fetches nothing until opened', () => {
    const answer = vi.spyOn(api, 'answerProvenance').mockResolvedValue(view())
    const trigger = setup({ outputId: 'out-1' })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(answer).not.toHaveBeenCalled()
    expect(screen.queryByText('Model')).toBeNull()
  })

  it('opening fetches the answer and shows its rows', async () => {
    const answer = vi.spyOn(api, 'answerProvenance').mockResolvedValue(view())
    const trigger = setup({ outputId: 'out-1' })
    fireEvent.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    expect(await screen.findByText('qwen3:14b')).toBeInTheDocument()
    expect(answer).toHaveBeenCalledWith('out-1')
    expect(screen.getByText('Model')).toBeInTheDocument()
    expect(screen.getByText('Connection')).toBeInTheDocument()
    expect(screen.getByText('Home server')).toBeInTheDocument()
    expect(screen.getByText('Prompt version')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('Made')).toBeInTheDocument()
    expect(screen.getByText(new Date(CREATED).toLocaleString())).toBeInTheDocument()
  })

  it('shows the Skill row only when a skill was set', async () => {
    vi.spyOn(api, 'answerProvenance').mockResolvedValue(view({ skill_label: 'Literature review' }))
    setup({ outputId: 'out-1' })
    fireEvent.click(screen.getByRole('button', { name: 'How this was made' }))
    expect(await screen.findByText('Literature review')).toBeInTheDocument()
    expect(screen.getByText('Skill')).toBeInTheDocument()
  })

  it('leaves the Skill row out when none was set', async () => {
    vi.spyOn(api, 'answerProvenance').mockResolvedValue(view())
    setup({ outputId: 'out-1' })
    fireEvent.click(screen.getByRole('button', { name: 'How this was made' }))
    await screen.findByText('qwen3:14b')
    expect(screen.queryByText('Skill')).toBeNull()
  })

  it('names each passage with its paper, page and state', async () => {
    vi.spyOn(api, 'answerProvenance').mockResolvedValue(
      view({
        passages: [
          { label: 'C1', paper_id: PAPER, paper_title: 'Paper A', page: 4, section: null, text: 'x', state: 'current' },
          { label: 'C2', paper_id: PAPER, paper_title: 'Paper B', page: 7, section: null, text: 'y', state: 'changed' },
          { label: 'C3', paper_id: null, paper_title: null, page: null, section: null, text: null, state: 'not_recorded' },
        ],
      }),
    )
    setup({ outputId: 'out-1' })
    fireEvent.click(screen.getByRole('button', { name: 'How this was made' }))
    expect(await screen.findByText(/Paper A, p\. 4/)).toBeInTheDocument()
    expect(screen.getByText('Still in the paper')).toBeInTheDocument()
    expect(screen.getByText(/Paper B, p\. 7/)).toBeInTheDocument()
    expect(screen.getByText('No longer matches the paper')).toBeInTheDocument()
    expect(screen.getByText('C3')).toBeInTheDocument()
    expect(screen.getByText('Not recorded for answers saved before this was added.')).toBeInTheDocument()
  })

  it('shows the out-of-date banner only when a cited passage changed', async () => {
    const answer = vi.spyOn(api, 'answerProvenance')
    answer.mockResolvedValueOnce(view({ out_of_date: false }))
    setup({ outputId: 'out-1' })
    fireEvent.click(screen.getByRole('button', { name: 'How this was made' }))
    await screen.findByText('qwen3:14b')
    expect(screen.queryByText(/Some passages this answer cited have changed/)).toBeNull()
  })

  it('shows the banner when out of date', async () => {
    vi.spyOn(api, 'answerProvenance').mockResolvedValue(view({ out_of_date: true }))
    setup({ outputId: 'out-1' })
    fireEvent.click(screen.getByRole('button', { name: 'How this was made' }))
    expect(await screen.findByText('Some passages this answer cited have changed since. Ask again for a current answer.')).toBeInTheDocument()
  })

  it('an AI note reads its answer, and an MCP note says only where it came from', async () => {
    const note = vi.spyOn(api, 'noteProvenance').mockResolvedValue({ source: 'claude_desktop' })
    setup({ noteId: 'n-1' })
    fireEvent.click(screen.getByRole('button', { name: 'How this was made' }))
    expect(await screen.findByText('Added from Claude Desktop.')).toBeInTheDocument()
    expect(note).toHaveBeenCalledWith('n-1')
    expect(screen.queryByText('Model')).toBeNull()
  })

  it('an AI note with a saved answer shows its rows', async () => {
    vi.spyOn(api, 'noteProvenance').mockResolvedValue(view({ model: 'gemma3' }))
    setup({ noteId: 'n-2' })
    fireEvent.click(screen.getByRole('button', { name: 'How this was made' }))
    expect(await screen.findByText('gemma3')).toBeInTheDocument()
  })

  it('a failed load says so instead of showing nothing', async () => {
    vi.spyOn(api, 'answerProvenance').mockRejectedValue(new Error('boom'))
    setup({ outputId: 'out-1' })
    fireEvent.click(screen.getByRole('button', { name: 'How this was made' }))
    await waitFor(() => expect(screen.getByText('Could not load how this was made.')).toBeInTheDocument())
  })
})
