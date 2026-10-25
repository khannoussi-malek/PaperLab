import { createElement, Fragment, type ReactNode } from 'react'
import type { Piece, Tag } from './markdown'

/** How each markdown element looks inside an answer; the answer's own size and leading come from its container. */
export const MARKDOWN_CLASS: Partial<Record<Tag, string>> = {
  h1: 'text-base font-semibold',
  h2: 'text-base font-semibold',
  h3: 'font-semibold',
  h4: 'font-semibold',
  h5: 'font-semibold',
  h6: 'font-semibold',
  strong: 'font-semibold',
  ul: 'list-disc space-y-1 pl-5',
  ol: 'list-decimal space-y-1 pl-5',
  li: 'space-y-1 marker:text-muted-foreground',
  blockquote: 'border-l-2 border-glass-border pl-3 text-muted-foreground',
  pre: 'overflow-x-auto rounded-lg bg-background/70 p-2.5 text-xs whitespace-pre [&>code]:bg-transparent [&>code]:p-0',
  code: 'rounded bg-background/70 px-1 py-0.5 font-mono text-[0.9em]',
  a: 'text-primary underline underline-offset-2',
  table: 'w-full border-collapse text-xs',
  th: 'border-b border-glass-border px-2 py-1 text-left font-semibold',
  td: 'border-b border-glass-border px-2 py-1 align-top',
  hr: 'border-glass-border',
}

/** Markdown pieces as elements. Syntax stays in the DOM, `hidden`, so the answer's text keeps every character. */
export function renderPieces(pieces: Piece[], renderText: (text: string) => ReactNode): ReactNode[] {
  return pieces.map((piece, i) => {
    if (piece.kind !== 'element') {
      return piece.kind === 'hidden' ? <span key={i} hidden>{piece.text}</span> : <Fragment key={i}>{renderText(piece.text)}</Fragment>
    }
    const { tag, href, start, children } = piece
    const props = { key: i, className: MARKDOWN_CLASS[tag], href, start, target: href && '_blank', rel: href && 'noreferrer' }
    // A void element like <hr> must get no children at all, not even an empty list.
    const element = createElement(tag, props, ...(children.length ? [renderPieces(children, renderText)] : []))
    return tag === 'table' ? <div key={i} className="overflow-x-auto">{element}</div> : element
  })
}
