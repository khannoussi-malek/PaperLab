const CITE = /\\[A-Za-z]*[Cc]ite[A-Za-z]*\*?(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]*)\}/g

/** The citation key under offset `at` of one line, when it is inside the braces of a \cite… key list. */
export function citeKeyAt(line: string, at: number): string | null {
  const live = line.replace(/(?<!\\)%.*/, (c) => ' '.repeat(c.length)) // a commented cite is not a cite
  for (const m of live.matchAll(CITE)) {
    const start = m.index + m[0].length - 1 - m[1].length
    if (at < start || at > start + m[1].length) continue
    let from = start
    for (const part of m[1].split(',')) {
      if (at <= from + part.length) return part.trim() || null
      from += part.length + 1
    }
  }
  return null
}
