import { describe, expect, it } from 'vitest'
import type { Dataset } from '@/api/client'
import { datasetToTable, parsePasted, toBooktabs } from './table'

const opts = { decimals: null, best: 'none' as const, caption: 'Results.', label: 'tab:r' }
const texts = (t: ReturnType<typeof parsePasted>) => t.rows.map((r) => r.map((c) => c.raw))

describe('parsePasted', () => {
  it('reads Excel TSV with quoted cells holding tabs and newlines', () => {
    const t = parsePasted('Name\tNote\nA\t"x\ty\nz"\n')
    expect(t.headers).toEqual(['Name', 'Note'])
    expect(texts(t)).toEqual([['A', 'x\ty\nz']])
  })
  it('reads CSV with quoted commas and doubled quotes', () => {
    expect(texts(parsePasted('a,b\n"x, y","say ""hi"""'))).toEqual([['x, y', 'say "hi"']])
  })
  it('drops empty trailing rows and columns, pads ragged rows', () => {
    const t = parsePasted('a,b,c,\n1,2\n3,4,5,\n,,,\n\n')
    expect(t.headers).toEqual(['a', 'b', 'c'])
    expect(texts(t)).toEqual([['1', '2', ''], ['3', '4', '5']])
  })
  it('handles thousands separators for dot decimals only', () => {
    const t = parsePasted('a\tb\n1,234.5\t1.234,5')
    expect(t.rows[0].map((c) => c.value)).toEqual([1234.5, null])
  })
  it('parses ± errors, +-, percent and NaN', () => {
    const t = parsePasted('a\tb\tc\td\n0.91 ± 0.02\t0.5 +- 0.1\t85%\tNaN')
    expect(t.rows[0]).toEqual([
      { raw: '0.91 ± 0.02', value: 0.91, error: 0.02 },
      { raw: '0.5 +- 0.1', value: 0.5, error: 0.1 },
      { raw: '85%', value: 85, error: null },
      { raw: 'NaN', value: null, error: null },
    ])
  })
})

describe('toBooktabs', () => {
  it('writes the plain table', () => {
    expect(toBooktabs(parsePasted('Model\tF1\nBERT\t88.5\nGPT\t90'), opts)).toBe(
      [
        '\\begin{table}[t]', '\\centering', '\\begin{tabular}{lr}', '\\toprule', 'Model & F1 \\\\', '\\midrule',
        'BERT & 88.5 \\\\', 'GPT & 90 \\\\', '\\bottomrule', '\\end{tabular}', '\\caption{Results.}', '\\label{tab:r}', '\\end{table}',
      ].join('\n'),
    )
  })
  it('applies decimals and best value, with errors as math', () => {
    const t = parsePasted('Model\tF1\nA\t0.9 ± 0.02\nB\t0.85\nC\t')
    const out = toBooktabs(t, { ...opts, decimals: 2, best: 'max' })
    expect(out).toContain('A & \\textbf{$0.90 \\pm 0.02$} \\\\')
    expect(out).toContain('B & 0.85 \\\\')
    expect(out).toContain('C &  \\\\')
    expect(toBooktabs(t, { ...opts, best: 'min' })).toContain('B & \\textbf{0.85} \\\\')
    expect(toBooktabs(t, opts)).toContain('A & $0.9 \\pm 0.02$ \\\\')
  })
  it('escapes specials, keeps text columns left, percent stays escaped', () => {
    const out = toBooktabs(parsePasted('A_b\tc\nx & y\t85%\nz\tno'), opts)
    expect(out).toContain('{ll}')
    expect(out).toContain('A\\_b & c \\\\')
    expect(out).toContain('x \\& y & 85\\% \\\\')
    expect(toBooktabs(parsePasted('a\tb\nx\t85%'), { ...opts, decimals: 1 })).toContain('x & 85.0\\% \\\\')
  })
})

describe('datasetToTable', () => {
  const cell = (column_id: string, raw: string, value: number | null, error: number | null) => ({ column_id, raw, value, error })
  const detail = {
    kind: 'table', paper_id: 'p1', paper_title: 'A Paper',
    columns: [{ id: 'c2', position: 1, name: 'F1', unit: '%' }, { id: 'c1', position: 0, name: 'Model', unit: null }],
    rows: [{ id: 'r1', position: 0, cells: [cell('c2', '88 ± 1', 88, 1), cell('c1', 'BERT', null, null)] }],
  } as unknown as Dataset
  it('orders by position, appends units and sets the source', () => {
    expect(datasetToTable(detail)).toEqual({
      headers: ['Model', 'F1 (%)'],
      rows: [[{ raw: 'BERT', value: null, error: null }, { raw: '88 ± 1', value: 88, error: 1 }]],
      source: { paperId: 'p1', paperTitle: 'A Paper' },
    })
  })
  it('has no source for user datasets', () => {
    expect(datasetToTable({ ...detail, kind: 'user' } as Dataset).source).toBeUndefined()
  })
})
