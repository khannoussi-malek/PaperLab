/** A piece of an answer: plain text, or a `[C<n>]` marker for a known source label. */
export type Segment = { kind: 'text'; text: string } | { kind: 'cite'; label: string }

export const MARKER = /\[(C\d{1,3})\]/g
// ponytail: up to 3 digits, so at most 999 sources per answer; widen both patterns if k ever gets there.
const PARTIAL = /\[(?:C\d{0,3})?$/

/**
 * Splits a token stream into segments as it arrives. A trailing `[`, `[C` or `[C12` is held back until the next
 * token decides whether it is a marker, so a citation never flashes as text first. Unknown labels stay text.
 */
export function citationSplitter(known: ReadonlySet<string>) {
  let buffer = ''
  return {
    feed(token: string): Segment[] {
      buffer += token
      const out: Segment[] = []
      let position = 0
      for (const match of buffer.matchAll(MARKER)) {
        if (!known.has(match[1])) continue // stays inside the next text slice
        if (match.index > position) out.push({ kind: 'text', text: buffer.slice(position, match.index) })
        out.push({ kind: 'cite', label: match[1] })
        position = match.index + match[0].length
      }
      const rest = buffer.slice(position)
      const cut = PARTIAL.exec(rest)?.index ?? rest.length
      if (cut > 0) out.push({ kind: 'text', text: rest.slice(0, cut) })
      buffer = rest.slice(cut)
      return out
    },
    flush(): Segment[] {
      const out: Segment[] = buffer ? [{ kind: 'text', text: buffer }] : []
      buffer = ''
      return out
    },
  }
}

/** Segments for a finished answer, e.g. one loaded from history. */
export function splitCitations(content: string, known: ReadonlySet<string>): Segment[] {
  const splitter = citationSplitter(known)
  return [...splitter.feed(content), ...splitter.flush()]
}

/** Appends newly streamed segments, merging adjacent text so the answer renders as few spans as possible. */
export function appendSegments(segments: Segment[], added: Segment[]): Segment[] {
  return added.reduce((merged, segment) => {
    const last = merged.at(-1)
    return segment.kind === 'text' && last?.kind === 'text'
      ? [...merged.slice(0, -1), { kind: 'text', text: last.text + segment.text }]
      : [...merged, segment]
  }, segments)
}
