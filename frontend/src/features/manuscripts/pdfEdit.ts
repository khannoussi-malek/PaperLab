export type Span = { line: number; start: number; end: number }

const NEIGHBOURS = [0, -1, 1, -2, 2, -3, 3]
const edge = /^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** The line with every `\command` blanked out (same length), so words inside commands never match. */
const masked = (line: string) => line.replace(/\\[a-zA-Z]+\*?/g, (c) => ' '.repeat(c.length))

/** The sentence of `line` (split at . ? ! before a space, or the line's ends) that holds the word at `index`. */
export function sentenceAt(line: string, index: number): { start: number; end: number } {
  let start = 0
  for (const m of line.matchAll(/[.?!]\s+/g)) {
    const next = m.index + m[0].length
    if (index < next) return { start, end: m.index + 1 }
    start = next
  }
  return { start, end: line.trimEnd().length }
}

/**
 * The sentence holding `word` as a whole word, on `line` (1-based) or up to three lines either side of it (the PDF may
 * be older than the source). Null when the word is not in that source: generated text (a citation label, a number).
 */
export function findEditable(lines: string[], line: number, word: string): Span | null {
  const w = word.replace(edge, '')
  if (!w) return null
  const re = new RegExp(`(?<![\\p{L}\\p{N}])${escape(w)}(?![\\p{L}\\p{N}])`, 'u')
  for (const d of NEIGHBOURS) {
    const at = line + d
    const text = lines[at - 1]
    if (text === undefined) continue
    const hit = re.exec(masked(text))
    if (hit) return { line: at, ...sentenceAt(masked(text), hit.index) }
  }
  return null
}

export function replaceSpan(text: string, at: Span, replacement: string): string {
  const lines = text.split('\n')
  const row = lines[at.line - 1] ?? ''
  return [...lines.slice(0, at.line - 1), row.slice(0, at.start) + replacement + row.slice(at.end), ...lines.slice(at.line)].join('\n')
}
