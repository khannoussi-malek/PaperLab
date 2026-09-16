import { describe, expect, it } from 'vitest'
import { markdownPieces, type Piece } from './markdown'

/** All text, hidden syntax included: what the answer element's textContent will be. */
const all = (pieces: Piece[]): string => pieces.map((p) => (p.kind === 'element' ? all(p.children) : p.text)).join('')
/** What the reader sees. */
const visible = (pieces: Piece[]): string =>
  pieces.map((p) => (p.kind === 'element' ? visible(p.children) : p.kind === 'text' ? p.text : '')).join('')
/** The element tree alone, e.g. `ul(li(p))`. */
const shape = (pieces: Piece[]): string =>
  pieces
    .flatMap((p) => (p.kind === 'element' ? [`${p.tag}${p.children.some((c) => c.kind === 'element') ? `(${shape(p.children)})` : ''}`] : []))
    .join(' ')

const find = (pieces: Piece[], tag: string): Extract<Piece, { kind: 'element' }> | undefined =>
  pieces.flatMap((p) => (p.kind !== 'element' ? [] : p.tag === tag ? [p] : [find(p.children, tag)].filter((x) => !!x)))[0]

const SAMPLES = [
  'Plain answer [C1].',
  'Key findings include:\n\n- AI code is rarer on weekends [C2].\n- Fewer alerts [N2].\n\nDone.',
  '1. **RQ1: What?** Explores tests. [C27][C28]\n\n2. **RQ2** second\n   continued line',
  '## Heading\n\nText with `code` and *emphasis* and ~~gone~~.',
  '```python\nprint("x")\n```\n\nAfter the code.',
  '| Metric | AI | Human |\n|---|---|---|\n| Alerts | 1.2 | 2.0 [C3] |\n| Lines | 10 | 12 |\n',
  'See [the paper](https://example.com) and https://arxiv.org/abs/1.\n\n> quoted\n\n---\n\nEnd',
  'Streaming **bol',
  '```js\nconst unfinished = 1',
  '\n\n  leading space and trailing  \n\n',
  'Shown on page 4 [C1](p.4).',
  '',
]

describe('markdownPieces', () => {
  it.each(SAMPLES)('keeps every character of %j, so selection offsets still map onto the answer', (content) => {
    expect(all(markdownPieces(content))).toBe(content)
  })

  it('hides the syntax and keeps the words, markers included', () => {
    const pieces = markdownPieces('1. **RQ1: What?** Explores tests. [C27][C28]')
    expect(visible(pieces)).toBe('RQ1: What? Explores tests. [C27][C28]')
    expect(shape(pieces)).toBe('ol(li(p(strong)))')
  })

  it('lays out headings, lists, code and tables as elements', () => {
    expect(shape(markdownPieces(SAMPLES[1]))).toBe('p ul(li(p) li(p)) p')
    expect(shape(markdownPieces(SAMPLES[3]))).toBe('h2 p(code em del)')
    expect(shape(markdownPieces(SAMPLES[4]))).toBe('pre(code) p')
    expect(shape(markdownPieces(SAMPLES[5]))).toBe('table(thead(tr(th th th)) tbody(tr(td td td) tr(td td td)))')
    expect(visible(markdownPieces(SAMPLES[4]))).toBe('print("x")After the code.')
  })

  it('keeps an ordered list starting past 1 numbered from there', () => {
    expect(find(markdownPieces('3. third\n4. fourth'), 'ol')?.start).toBe(3)
  })

  it('never reads a citation marker as a link or a definition', () => {
    const pieces = markdownPieces(SAMPLES[10])
    expect(shape(pieces)).toBe('p')
    expect(visible(pieces)).toBe(SAMPLES[10])
  })

  it('links only web and mail addresses', () => {
    expect(find(markdownPieces('[x](https://example.com)'), 'a')?.href).toBe('https://example.com')
    const unsafe = markdownPieces('[click](javascript:alert(1))')
    expect(find(unsafe, 'a')).toBeUndefined()
    expect(visible(unsafe)).toBe('click')
  })
})
