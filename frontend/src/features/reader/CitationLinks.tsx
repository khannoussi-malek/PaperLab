import type { FocusEvent, KeyboardEvent, ReactNode } from 'react'
import { pdfRectToCss } from './coords'
import { citationCardId, type Citation } from './citations'

type Props = {
  citations: Citation[]
  scale: number
  /** The citation on this page whose card is open, if any. */
  openId: string | null
  /** The open card. It renders right after its button, so Tab goes from a citation into its card's actions, then on. */
  renderCard: (citation: Citation) => ReactNode
  onFocusIn: (citation: Citation) => void
  onFocusOut: (citation: Citation) => void
  onEscape: (citation: Citation) => void
  onJump: (citation: Citation) => void
}

/** Focus moving between a citation's button and its own card stays inside: only arriving or leaving counts. */
const fromOutside = (event: FocusEvent<HTMLElement>) => !event.currentTarget.contains(event.relatedTarget as Node | null)

/**
 * One transparent button per citation, over its link (D147): the keyboard's way to citations. The page overlay ignores
 * the mouse, so pointing and clicking stay with the reader's hit test; focus, Enter or Space, and Escape come here.
 */
export function CitationLinks({ citations, scale, openId, renderCard, onFocusIn, onFocusOut, onEscape, onJump }: Props) {
  function escape(event: KeyboardEvent<HTMLElement>, citation: Citation) {
    if (event.key !== 'Escape') return
    event.currentTarget.querySelector<HTMLButtonElement>('.citation-link')?.focus()
    onEscape(citation)
  }

  return citations.map((citation) => {
    const open = citation.id === openId
    return (
      // `contents`: a wrapper for focus and keys only, so the button and the card still sit on the overlay itself.
      <div
        key={citation.id}
        className="contents"
        data-citation-id={citation.id}
        onFocus={(event) => fromOutside(event) && onFocusIn(citation)}
        onBlur={(event) => fromOutside(event) && onFocusOut(citation)}
        onKeyDown={(event) => escape(event, citation)}
      >
        <button
          type="button"
          aria-label={`Reference ${citation.label}`}
          aria-expanded={open}
          aria-controls={open ? citationCardId(citation) : undefined}
          className="citation-link absolute rounded-xs outline-on-page-ring focus-visible:outline-2"
          style={pdfRectToCss(citation.rect, scale)}
          onClick={() => onJump(citation)}
        />
        {open && renderCard(citation)}
      </div>
    )
  })
}
