/** Preamble, labels and placement for a results block (a table or a figure) going into the manuscript. */

export const MAIN_CHANGED = 'The main file changed. Open it and try again.'

const BEGIN = '\\begin{document}'

/** Text to put at a 1-based line and 0-based column of the document. */
export type PreambleEdit = { line: number; col: number; text: string }

/** Where the real `\begin{document}` starts: one inside a comment doesn't count. -1 when there is none. */
export function beginDocumentAt(text: string): number {
  for (let at = text.indexOf(BEGIN); at !== -1; at = text.indexOf(BEGIN, at + 1)) {
    if (!/(^|[^\\])%/.test(text.slice(text.lastIndexOf('\n', at - 1) + 1, at))) return at
  }
  return -1
}

/** The edit that adds the missing packages to `mainText`, or null when nothing is missing. */
export function preambleEdit(mainText: string, packages: string[]): PreambleEdit | null {
  const next = ensurePackages(mainText, packages)
  if (next === null) return null
  const at = beginDocumentAt(mainText)
  const lines = mainText.slice(0, at).split('\n')
  return { line: lines.length, col: lines[lines.length - 1].length, text: next.slice(at, at + next.length - mainText.length) }
}

/** The packages the preamble loads, comments ignored. */
function loaded(preamble: string): Set<string> {
  const code = preamble.split('\n').map((l) => l.replace(/(^|[^\\])%.*/, '$1')).join('\n')
  const names = [...code.matchAll(/\\(?:usepackage|RequirePackage)(?:\[[^\]]*\])?\{([^}]*)\}/g)].flatMap((m) => m[1].split(','))
  return new Set(names.map((n) => n.trim()))
}

/**
 * `mainText` with the missing `\usepackage` lines (and pgfplots' compat setting) added just before `\begin{document}`;
 * null when nothing is missing.
 */
export function ensurePackages(mainText: string, packages: string[]): string | null {
  const at = beginDocumentAt(mainText)
  if (at === -1) throw new Error("The main file has no \\begin{document}, so there's nowhere to add packages.")
  const have = loaded(mainText.slice(0, at))
  const lines = [...new Set(packages)].filter((p) => !have.has(p)).flatMap((p) => [`\\usepackage{${p}}`, ...(p === 'pgfplots' ? ['\\pgfplotsset{compat=1.18}'] : [])])
  if (lines.length === 0) return null
  const lead = at === 0 || mainText[at - 1] === '\n' ? '' : '\n'
  return `${mainText.slice(0, at)}${lead}${lines.join('\n')}\n${mainText.slice(at)}`
}

/** The label-safe form of a dataset or chart name. */
export const slug = (name: string): string => name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'untitled'

/** A typed label safe in `\label{}` (each run of braces, `%`, `#`, `\` or spaces becomes `-`), unique against the texts; '' if nothing is left. */
export function typedLabel(texts: string[], typed: string): string {
  const clean = typed.trim().replace(/[{}%#\\\s]+/g, '-')
  return clean ? uniqueLabel(texts, clean) : ''
}

/** `base`, or `base-2`, `base-3`... when a `\label{}` in any of the texts already uses it. */
export function uniqueLabel(texts: string[], base: string): string {
  const used = new Set(texts.flatMap((t) => [...t.matchAll(/\\label\{([^}]*)\}/g)].map((m) => m[1].trim())))
  let n = 1
  while (used.has(n === 1 ? base : `${base}-${n}`)) n++
  return n === 1 ? base : `${base}-${n}`
}

/** The line breaks that put `text` on lines of its own: one before unless at a line start, one after unless at a line end. */
export function ownLine(text: string, atLineStart: boolean, atLineEnd: boolean): string {
  return `${atLineStart ? '' : '\n'}${text}${atLineEnd ? '' : '\n'}`
}
