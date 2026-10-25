// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Brief, Lens } from '@/api/client'
import { BriefCard } from './BriefCard'
import type { BriefStream } from './useBriefStream'

const lens = { id: 'key_ideas', label: 'Key ideas' } as Lens
const idle: BriefStream = { status: 'idle', lens: null, sources: null, segments: [], outputId: null, problem: null }
const source = { label: 'C1', page: 1, bbox: [0, 0, 1, 1] } as never
const saved = (over: Partial<Brief> = {}): Brief =>
  ({ id: 'b1', lens: 'key_ideas', content: 'The method [C1].', model: 'fake:m', created_at: '2026-10-01T00:00:00Z', stale: false, partial: false, sources: [source], ...over }) as Brief

function card(over: { saved?: Brief | null; stream?: BriefStream } = {}, onGenerate = vi.fn(), onCite = vi.fn()) {
  render(<BriefCard lens={lens} saved={over.saved ?? null} stream={over.stream ?? idle} onGenerate={onGenerate} onCite={onCite} />)
  return { onGenerate, onCite }
}

describe('BriefCard', () => {
  it('offers Generate brief before there is one', () => {
    const { onGenerate } = card()
    fireEvent.click(screen.getByRole('button', { name: 'Generate brief' }))
    expect(onGenerate).toHaveBeenCalled()
  })

  it('shows a saved brief with the AI badge, model and a citation that jumps', () => {
    const { onCite } = card({ saved: saved() })
    expect(screen.getByText('AI')).toBeInTheDocument()
    expect(document.querySelector('.brief-meta')).toHaveTextContent('fake:m')
    expect(screen.queryByText('Out of date: sections changed')).toBeNull()
    fireEvent.click(document.querySelector('.brief-cite')!)
    expect(onCite).toHaveBeenCalledWith(source)
  })

  it('says a stale brief is out of date and Regenerate writes a new one', () => {
    const { onGenerate } = card({ saved: saved({ stale: true }) })
    expect(screen.getByText('Out of date: sections changed')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Regenerate' }))
    expect(onGenerate).toHaveBeenCalled()
  })

  it('says a partial brief used part of the lens', () => {
    card({ saved: saved({ partial: true }) })
    expect(screen.getByText('Based on part of this lens')).toBeInTheDocument()
  })

  it('streams the text on the card of its own lens', () => {
    card({ stream: { ...idle, status: 'streaming', lens: 'key_ideas', segments: [{ kind: 'text', text: 'Writing now' }] } })
    expect(document.querySelector('.brief-text')).toHaveTextContent('Writing now')
  })

  it('shows chat\'s retryable error with Retry', () => {
    const { onGenerate } = card({ stream: { ...idle, status: 'error', lens: 'key_ideas', problem: { message: 'The model failed.', retryable: true, reindex: false } } })
    expect(screen.getByText('The model failed.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onGenerate).toHaveBeenCalled()
  })

  it('offers no Retry for a refusal that cannot be retried', () => {
    card({ stream: { ...idle, status: 'error', lens: 'key_ideas', problem: { message: "Lenses read a paper's sections. Attach its PDF to use them.", retryable: false, reindex: false } } })
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull()
  })

  it('keeps the saved brief below the error when a new brief fails', () => {
    card({
      saved: saved({ stale: true }),
      stream: { ...idle, status: 'error', lens: 'key_ideas', problem: { message: 'The model failed.', retryable: true, reindex: false } },
    })
    expect(screen.getByText('The model failed.')).toBeInTheDocument()
    expect(document.querySelector('.brief-text')).toHaveTextContent('The method')
    expect(document.querySelector('.brief-meta')).toHaveTextContent('fake:m')
  })
})
