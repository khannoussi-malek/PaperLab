// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Paper } from '@/api/client'
import { SourceBadges } from './SourceBadges'

const paper = (over: Partial<Paper>) =>
  ({ source_type: null, peer_reviewed: 'unknown', evidence_access: 'metadata', ...over }) as Paper

describe('SourceBadges', () => {
  it('shows the type, peer review and evidence access', () => {
    render(<SourceBadges paper={paper({ source_type: 'journal_article', peer_reviewed: 'true', evidence_access: 'full_text' })} />)
    expect(screen.getByText('Journal article')).toBeInTheDocument()
    expect(screen.getByText('Peer-reviewed')).toBeInTheDocument()
    expect(screen.getByText('Full text')).toBeInTheDocument()
  })

  it('calls an unreviewed preprint what it is', () => {
    render(<SourceBadges paper={paper({ source_type: 'preprint', peer_reviewed: 'false', evidence_access: 'abstract' })} />)
    expect(screen.getByText('Preprint')).toBeInTheDocument()
    expect(screen.getByText('Preprint · not peer-reviewed')).toBeInTheDocument()
    expect(screen.getByText('Abstract only')).toBeInTheDocument()
  })

  it('shows no type or peer-review chip when both are unknown', () => {
    render(<SourceBadges paper={paper({})} />)
    expect(screen.getByText('Metadata only')).toBeInTheDocument()
    expect(screen.queryByText(/peer-reviewed/i)).toBeNull()
    expect(document.querySelectorAll('[data-slot="badge"]')).toHaveLength(1)
  })

  describe('a preprint copy with a published version', () => {
    const copy = (over: Partial<Paper> = {}) =>
      paper({
        source_type: 'preprint', peer_reviewed: 'true', year: 2025, published_doi: '10.18653/v1/2025.emnlp-main.1',
        published_venue: 'Conference on Empirical Methods in Natural Language Processing', ...over,
      })

    it('shows one Published chip with the full venue, truncated by CSS', () => {
      render(<SourceBadges paper={copy()} />)
      const chip = document.querySelector('.published-version')
      expect(chip).toHaveTextContent(
        'Published: Conference on Empirical Methods in Natural Language Processing 2025',
      )
      expect(screen.getByTitle('Conference on Empirical Methods in Natural Language Processing')).toHaveClass('truncate')
      expect(screen.queryByText('Preprint')).toBeNull()
      expect(screen.queryByText('Peer-reviewed')).toBeNull()
    })

    it('uses the acronym, links the DOI, and its accessible name is the visible text', () => {
      render(<SourceBadges paper={copy({ published_venue: 'Symposium on Theory of Computing (STOC)', published_doi: '10.1145/3717823.3718108' })} />)
      const link = screen.getByRole('link', { name: 'Published: STOC 2025' })
      expect(link).toHaveAttribute('href', 'https://doi.org/10.1145/3717823.3718108')
      expect(link).not.toHaveAttribute('aria-label')
    })

    it('is plain text without a DOI', () => {
      render(<SourceBadges paper={copy({ published_doi: null })} />)
      expect(screen.queryByRole('link')).toBeNull()
    })
  })

  it('keeps Preprint for a pure arXiv copy', () => {
    render(<SourceBadges paper={paper({ source_type: 'preprint', peer_reviewed: 'false' })} />)
    expect(screen.getByText('Preprint')).toBeInTheDocument()
    expect(screen.queryByText(/Published/)).toBeNull()
  })

  it('keeps Peer-reviewed for a journal paper with its own DOI', () => {
    render(<SourceBadges paper={paper({ source_type: 'journal_article', peer_reviewed: 'true', published_doi: '10.1/x' })} />)
    expect(screen.getByText('Peer-reviewed')).toBeInTheDocument()
    expect(screen.queryByText(/Published:/)).toBeNull()
  })

  it('says "No PDF yet" for a paper saved without one, and nothing about the PDF otherwise', () => {
    const { unmount } = render(<SourceBadges paper={paper({ has_pdf: false, evidence_access: 'abstract' })} />)
    expect(screen.getByText('No PDF yet')).toHaveClass('no-pdf')
    unmount()
    render(<SourceBadges paper={paper({ has_pdf: true, evidence_access: 'full_text' })} />)
    expect(screen.queryByText('No PDF yet')).toBeNull()
  })
})
