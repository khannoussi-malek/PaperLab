export type OutlineItem = { level: 1 | 2 | 3; title: string; file: string; line: number }

const LEVELS = { section: 1, subsection: 2, subsubsection: 3 } as const
// A heading, or an \input / \include to follow.
const TOKEN = /\\(subsubsection|subsection|section)\*?(?:\[[^\]]*\])?\{([^}]*)\}|\\(?:input|include)\{([^}]+)\}/g
export const COMMENT = /(^|[^\\])%.*/

export const texName = (name: string) => (name.trim().endsWith('.tex') ? name.trim() : `${name.trim()}.tex`)

/** The headings of `main`, in reading order, descending into each \input / \include once. */
export function outline(files: Record<string, string>, main: string): OutlineItem[] {
  const seen = new Set<string>()
  const walk = (file: string): OutlineItem[] => {
    const text = files[file]
    if (text === undefined || seen.has(file)) return []
    seen.add(file)
    const items: OutlineItem[] = []
    text.split('\n').forEach((raw, index) => {
      for (const m of raw.replace(COMMENT, '$1').matchAll(TOKEN)) {
        if (m[1]) items.push({ level: LEVELS[m[1] as keyof typeof LEVELS], title: m[2].trim(), file, line: index + 1 })
        else items.push(...walk(texName(m[3])))
      }
    })
    return items
  }
  return walk(main)
}

/** The section and subsection(s) containing `line` (1-based) of `file`, outermost first. */
export function crumbsAt(items: OutlineItem[], file: string, line: number): OutlineItem[] {
  const crumbs: OutlineItem[] = []
  for (const item of items) {
    if (item.file !== file || item.line > line) continue
    crumbs.splice(item.level - 1)
    crumbs[item.level - 1] = item
  }
  return crumbs.filter(Boolean)
}
