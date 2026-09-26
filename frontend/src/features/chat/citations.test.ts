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

  it('splits note markers like passage markers, holding back a partial [N', () => {
    const known = new Set(['C1', 'C2', 'N1'])
    expect(run(['both describe it [C1][C2], as your note says [N', '1].'], known)).toEqual([
      text('both describe it '), cite('C1'), cite('C2'), text(', as your note says '), cite('N1'), text('.'),
    ])
  })

  it('leaves an unknown note marker, or any other letter, as plain text', () => {
    expect(run(['[N9] and [X1] and [N1]'], new Set(['N1']))).toEqual([text('[N9] and [X1] and '), cite('N1')])
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

  it('names the paper first when an answer cites several papers', () => {
    expect(describeSource(source, 'Karpukhin 2020')).toBe('Source 12: Karpukhin 2020, page 6, section “2.4 Analysis”')
  })

  it('describes a [N…] note as a note, with who wrote it and where, never as a numbered source', () => {
    const note = { label: 'N1', note_id: 'n', paper_id: 'p', page: 4, provenance: 'human' as const }
    expect(describeSource(note, 'BERT')).toBe('N1 · You · BERT p.4')
    expect(describeSource({ ...note, label: 'N2', provenance: 'llm_edited' }, 'BERT')).toBe('N2 · AI · edited · BERT p.4')
  })

  it('names a note on the whole paper by its paper alone, with no page', () => {
    const whole = { label: 'N2', note_id: 'n', paper_id: 'p', page: null, provenance: 'llm' as const }
    expect(describeSource(whole, 'Devlin 2019')).toBe('N2 · AI · Devlin 2019')
    expect(describeSource(whole)).toBe('N2 · AI')
  })
})
