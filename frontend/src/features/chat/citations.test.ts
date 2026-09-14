import { describe, expect, it } from 'vitest'
import { appendSegments, citationSplitter, describeSource, splitCitations, type Segment } from './citations'

const KNOWN = new Set(['C1', 'C2', 'C3', 'C12'])
const text = (value: string): Segment => ({ kind: 'text', text: value })
const cite = (label: string): Segment => ({ kind: 'cite', label })

/** Feeds tokens like a stream, then flushes, merging adjacent text the way the answer view does. */
function run(tokens: string[], known: ReadonlySet<string> = KNOWN): Segment[] {
  const splitter = citationSplitter(known)
  return appendSegments([], [...tokens.flatMap((token) => splitter.feed(token)), ...splitter.flush()])
}

describe('citationSplitter', () => {
  it('splits a marker inside one token', () => {
    expect(run(['Attention [C1] works.'])).toEqual([text('Attention '), cite('C1'), text(' works.')])
  })

  it('splits adjacent markers', () => {
    expect(run(['see [C1][C3].'])).toEqual([text('see '), cite('C1'), cite('C3'), text('.')])
  })

  it('joins a marker split across two tokens', () => {
    expect(run(['all [C', '1] you'])).toEqual([text('all '), cite('C1'), text(' you')])
  })

  it("handles Ollama's real tokenization, where '][' and '].' are single tokens", () => {
    // Recorded from qwen2.5:7b via Ollama /api/chat (M4 spike, out_ollama.txt).
    const tokens = [
      'Attention', ' works', ' [', 'C', '1', '][', 'C', '3', '].', ' See', ' [', 'C', '1', '2', ']',
      ' and', ' [', 'C', '2', '].',
    ]
    expect(run(tokens)).toEqual([
      text('Attention works '), cite('C1'), cite('C3'), text('. See '), cite('C12'), text(' and '), cite('C2'), text('.'),
    ])
  })

  it('leaves an unknown marker as plain text', () => {
    expect(run(['x [C9] y [C', '2]'])).toEqual([text('x [C9] y '), cite('C2')])
  })

  it('holds back a partial marker until the next token decides it', () => {
    const splitter = citationSplitter(new Set(['C1']))
    expect(splitter.feed('end [C')).toEqual([text('end ')])
    expect(splitter.feed('1')).toEqual([])
    expect(splitter.feed('] ok')).toEqual([cite('C1'), text(' ok')])
  })

  it("releases a held-back '[C' as text when a non-digit follows, as in BERT's [CLS]", () => {
    expect(run(['the [C', 'LS] token [C1]'])).toEqual([text('the [CLS] token '), cite('C1')])
  })

  it.each([['arr[0] and [Cat]'], ['trailing ['], ['[C1234]'], ['[c1]']])('passes %j through as text', (value) => {
    expect(run([value])).toEqual([text(value)])
  })

  it('renders a repeated marker every time it appears', () => {
    expect(run(['[C2] a [C2]'])).toEqual([cite('C2'), text(' a '), cite('C2')])
  })
})

describe('splitCitations', () => {
  it('splits a finished answer in one go, including a trailing marker', () => {
    expect(splitCitations('Done [C1]', new Set(['C1']))).toEqual([text('Done '), cite('C1')])
  })
})

describe('describeSource', () => {
  const source = { label: 'C12', chunk_id: 'x', page: 6, section: '2.4 Analysis', bbox: [] }

  it('says in words which passage a [C…] marker points at', () => {
    expect(describeSource(source)).toBe('Source 12: page 6, section “2.4 Analysis”')
  })

  it('leaves out the section when the passage has none', () => {
    expect(describeSource({ ...source, section: null })).toBe('Source 12: page 6')
  })
})
