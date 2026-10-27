import type { Dataset } from '@/api/client'
import { latexEscape } from '../deck/latex'

export type TableCell = { raw: string; value: number | null; error: number | null }
export type TableInput = { headers: string[]; rows: TableCell[][]; source?: { paperId: string; paperTitle: string } }
export type BooktabsOptions = { decimals: number | null; best: 'none' | 'max' | 'min'; caption: string; label: string }

const NUM = String.raw`[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|[+-]?\.\d+`
const PM = String.raw`\s*(?:±|\+-|\+/-)\s*`
const PM_SPLIT = /\s*(?:±|\+-|\+\/-)\s*/
const CELL = new RegExp(`^(${NUM})%?(?:${PM}(${NUM})%?)?$`)
const plain = (s: string) => Number(s.replace(/,/g, ''))

/** A pasted cell: a number, optionally `± error` and `%`; anything else (including `1.234,5`) stays text. */
const toCell = (text: string): TableCell => {
  const raw = text
  const m = CELL.exec(raw.trim())
  return { raw, value: m ? plain(m[1]) : null, error: m?.[2] ? plain(m[2]) : null }
}

/** RFC 4180 reader with a chosen delimiter: quoted fields keep delimiters and newlines, `""` is a quote. */
function splitRecords(input: string, delim: string): string[][] {
  const text = input.replace(/^\ufeff/, '')
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false
  let wasQuoted = false
  const endField = () => {
    row.push(wasQuoted ? field : field.trim())
    field = ''
    wasQuoted = false
  }
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (quoted) {
      if (c !== '"') field += c
      else if (text[i + 1] === '"') {
        field += '"'
        i++
      } else quoted = false
    } else if (c === '"' && !wasQuoted && field.trim() === '') {
      quoted = wasQuoted = true
      field = ''
    } else if (c === delim) endField()
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++
      endField()
      rows.push(row)
      row = []
    } else if (!wasQuoted || c.trim() !== '') field += c
  }
  endField()
  rows.push(row)
  return rows
}

/** TSV if any line has a tab, else CSV; the first row is the headers. Ragged rows are padded, empty trailing rows and columns dropped. */
export function parsePasted(text: string): TableInput {
  const grid = splitRecords(text, text.includes('\t') ? '\t' : ',')
  while (grid.length && grid[grid.length - 1].every((f) => f === '')) grid.pop()
  const width = grid.reduce((w, r) => {
    const last = r.findLastIndex((f) => f !== '')
    return Math.max(w, last + 1)
  }, 0)
  const padded = grid.map((r) => Array.from({ length: width }, (_, i) => r[i] ?? ''))
  const [headers = [], ...body] = padded
  return { headers, rows: body.map((r) => r.map(toCell)) }
}

/** A saved dataset: columns and rows by position, cells matched by column id. */
export function datasetToTable(detail: Dataset): TableInput {
  const columns = [...detail.columns].sort((a, b) => a.position - b.position)
  const rows = [...detail.rows].sort((a, b) => a.position - b.position)
  const source = detail.kind === 'table' && detail.paper_id ? { paperId: detail.paper_id, paperTitle: detail.paper_title ?? '' } : undefined
  return {
    headers: columns.map((c) => (c.unit ? `${c.name} (${c.unit})` : c.name)),
    rows: rows.map((row) =>
      columns.map((c) => {
        const cell = row.cells.find((x) => x.column_id === c.id)
        return cell ? { raw: cell.raw, value: cell.value, error: cell.error } : { raw: '', value: null, error: null }
      }),
    ),
    ...(source && { source }),
  }
}

const oneLine = (text: string) => latexEscape(text.replace(/\s*[\n\r\t]+\s*/g, ' '))

const showNumber = (cell: TableCell, decimals: number | null): string => {
  if (cell.value === null) return oneLine(cell.raw)
  const [first, second] = cell.raw.trim().split(PM_SPLIT)
  const clean = CELL.test(cell.raw.trim())
  const num = (n: number, pct: boolean) => (decimals === null ? String(n) : n.toFixed(decimals)) + (pct ? '\\%' : '')
  if (clean && decimals === null) {
    if (second !== undefined) return `$${latexEscape(first)} \\pm ${latexEscape(second)}$`
    return cell.error === null ? oneLine(cell.raw.trim()) : `$${latexEscape(first)} \\pm ${cell.error}$`
  }
  const v = num(cell.value, /^\s*[+-]?[\d.,]+\s*%/.test(cell.raw))
  if (cell.error === null) return decimals === null ? oneLine(cell.raw) : v
  return `$${v} \\pm ${num(cell.error, clean && !!second?.includes('%'))}$`
}

export function toBooktabs(t: TableInput, opts: BooktabsOptions): string {
  if (t.headers.length === 0) throw new Error('The table has no columns.')
  const numeric = t.headers.map((_, c) => {
    const filled = t.rows.map((r) => r[c]).filter((x) => x && x.raw.trim() !== '')
    return c > 0 && filled.length > 0 && filled.every((x) => x.value !== null)
  })
  const best = numeric.map((isNum, c) => {
    if (!isNum || opts.best === 'none') return null
    const vals = t.rows.flatMap((r) => (r[c]?.value != null ? [r[c].value as number] : []))
    return Math.max(...vals.map((v) => (opts.best === 'max' ? v : -v))) * (opts.best === 'max' ? 1 : -1)
  })
  const line = (cells: string[]) => `${cells.join(' & ')} \\\\`
  const body = t.rows.map((r) =>
    line(
      t.headers.map((_, c) => {
        const cell = r[c] ?? { raw: '', value: null, error: null }
        if (!numeric[c] || cell.raw.trim() === '') return oneLine(cell.raw)
        const text = showNumber(cell, opts.decimals)
        return best[c] !== null && cell.value === best[c] ? `\\textbf{${text}}` : text
      }),
    ),
  )
  return [
    '\\begin{table}[t]',
    '\\centering',
    `\\begin{tabular}{${numeric.map((n) => (n ? 'r' : 'l')).join('')}}`,
    '\\toprule',
    line(t.headers.map(oneLine)),
    '\\midrule',
    ...body,
    '\\bottomrule',
    '\\end{tabular}',
    `\\caption{${opts.caption}}`,
    `\\label{${opts.label}}`,
    '\\end{table}',
  ].join('\n')
}
