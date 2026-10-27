import { COMMENT, texName } from './outline'

export type SectionRow = { path: string; title: string; line: number; inMain: boolean; missing: boolean }

const INPUT = /\\(?:input|include)\{([^}]+)\}/g
const SECTION = /\\section\*?(?:\[[^\]]*\])?\{([^}]*)\}/
const uncomment = (raw: string) => raw.replace(COMMENT, '$1')

/** One row per \input / \include of `main`; with none, one per top-level \section of `main` itself. */
export function sectionRows(files: Record<string, string>, main: string): SectionRow[] {
  const lines = (files[main] ?? '').split('\n').map(uncomment)
  const rows: SectionRow[] = []
  lines.forEach((text, i) => {
    for (const m of text.matchAll(INPUT)) {
      const path = texName(m[1])
      const body = files[path]
      const title = body === undefined ? undefined : body.split('\n').map(uncomment).join('\n').match(SECTION)?.[1].trim()
      rows.push({ path, title: title || path.replace(/^.*\//, '').replace(/\.tex$/, ''), line: i + 1, inMain: false, missing: body === undefined })
    }
  })
  if (rows.length) return rows
  lines.forEach((text, i) => {
    const m = text.match(SECTION)
    if (m) rows.push({ path: main, title: m[1].trim(), line: i + 1, inMain: true, missing: false })
  })
  return rows
}

/** The section's text: its file, or for a row inside main the lines up to the next \section. */
export function sectionText(files: Record<string, string>, row: SectionRow): string {
  const text = files[row.path] ?? ''
  if (!row.inMain) return text
  const lines = text.split('\n')
  const rest = lines.slice(row.line)
  const stop = rest.findIndex((l) => SECTION.test(uncomment(l)) || /\\end\{document\}/.test(l))
  return lines.slice(row.line - 1, stop === -1 ? undefined : row.line + stop).join('\n')
}

const MATH_ENV = /\\begin\{(equation|align|eqnarray|gather|multline)\*?\}[\s\S]*?\\end\{\1\*?\}/g
const ARG_ONLY = /\\(?:cite[a-z]*|ref|eqref|label|input|include|bibliography|bibliographystyle|usepackage|documentclass)\*?(?:\[[^\]]*\])*\{[^}]*\}/g

/** Words a reader would see: no comments, math, commands or citation keys. */
export function wordCount(tex: string): number {
  const plain = tex
    .split('\n').map(uncomment).join('\n')
    .replace(MATH_ENV, ' ')
    .replace(/\\\[[\s\S]*?\\\]|\$\$[\s\S]*?\$\$|\$[^$]*\$/g, ' ')
    .replace(ARG_ONLY, ' ')
    .replace(/\\[a-zA-Z]+\*?/g, ' ')
  return plain.match(/[\p{L}\p{N}][\p{L}\p{N}'’-]*/gu)?.length ?? 0
}
