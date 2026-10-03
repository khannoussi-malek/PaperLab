// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Hit } from '@/api/client'
import { SuggestionChip } from './SuggestionChip'

const hit = (over: Partial<Hit>) => ({ suggestion: null, suggestion_reason: null, suggestion_note: null, ...over }) as Hit

describe('SuggestionChip', () => {
  it.each([
    [{ suggestion: 'include' }, 'Suggests: include'],
    [{ suggestion: 'exclude', suggestion_reason: 'wrong_study_type' }, 'Suggests: exclude · wrong study type'],
    [{ suggestion: 'unsure' }, 'Unsure'],
  ])('reads %o as %s', (over, text) => {
    render(<SuggestionChip hit={hit(over as Partial<Hit>)} />)
    expect(screen.getByText(text)).toBeInTheDocument()
  })

  it('carries the note as its title and is never a button', () => {
    render(<SuggestionChip hit={hit({ suggestion: 'include', suggestion_note: 'An RCT.' })} />)
    expect(screen.getByText('Suggests: include')).toHaveAttribute('title', 'An RCT.')
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('renders nothing without a suggestion', () => {
    const { container } = render(<SuggestionChip hit={hit({})} />)
    expect(container).toBeEmptyDOMElement()
  })
})
