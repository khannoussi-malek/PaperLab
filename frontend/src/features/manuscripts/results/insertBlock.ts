/** Preamble, labels and placement for a results block (a table or a figure) going into the manuscript. */

export const MAIN_CHANGED = 'The main file changed. Open it and try again.'

const BEGIN = '\\begin{document}'

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
  const at = mainText.indexOf(BEGIN)
  if (at === -1) throw new Error("The main file has no \\begin{document}, so there's nowhere to add packages.")
  const have = loaded(mainText.slice(0, at))
  const lines = [...new Set(packages)].filter((p) => !have.has(p)).flatMap((p) => [`\\usepackage{${p}}`, ...(p === 'pgfplots' ? ['\\pgfplotsset{compat=1.18}'] : [])])
  if (lines.length === 0) return null
  const lead = at === 0 || mainText[at - 1] === '\n' ? '' : '\n'
  return `${mainText.slice(0, at)}${lead}${lines.join('\n')}\n${mainText.slice(at)}`
}

/** The label-safe form of a dataset or chart name. */
export const slug = (name: string): string => name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'untitled'

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
