export type Blueprint = {
  title: string
  contributions: string[]
  notation: { symbol: string; meaning: string }[]
  targets: { id: string; min: number; max: number }[]
}

export const BLUEPRINT_PATH = 'blueprint.json'

const isStr = (v: unknown): v is string => typeof v === 'string'

/** Lenient on purpose: the backend check is the strict one. Null when the text is not a JSON object. */
export function parseBlueprint(text: string): Blueprint | null {
  let raw: unknown
  try { raw = JSON.parse(text) } catch { return null }
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return null
  const r = raw as Record<string, unknown>
  const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
  const words = typeof r.target_words === 'object' && r.target_words !== null ? Object.entries(r.target_words) : []
  return {
    title: isStr(r.title) ? r.title : '',
    contributions: list(r.contributions).filter(isStr),
    notation: list(r.notation).flatMap((n) => {
      const o = n as Record<string, unknown> | null
      return o && isStr(o.symbol) && isStr(o.meaning) ? [{ symbol: o.symbol, meaning: o.meaning }] : []
    }),
    targets: words.flatMap(([id, b]) =>
      Array.isArray(b) && b.length === 2 && b.every((x) => typeof x === 'number') ? [{ id, min: b[0], max: b[1] }] : []),
  }
}

/** The starter file: the title, empty lists and the template's word bands. Pretty-printed, newline at the end. */
export function starterBlueprint(title: string, bands: Record<string, number[]> | undefined): string {
  return JSON.stringify({ title, contributions: [], notation: [], target_words: bands ?? {} }, null, 2) + '\n'
}

const TITLE = /\\title\s*(?:\[[^\]]*\]\s*)?\{/
const THANKS = /\\thanks\s*\{/
const BREAK = /\\\\|\\newline\b|~/g // ~ is a non-breaking space
const ESCAPED = /\\([%&$#_])/g
const LETTERS = /\\[A-Za-z]+\*?/g

/** Index just past the brace group opening at `open` (the text's end when it never closes). Mirrors _brace_end. */
function braceEnd(text: string, open: number): number {
  let depth = 0
  for (let i = open; i < text.length; i++) {
    if (text[i] === '\\') i++
    else if (text[i] === '{') depth++
    else if (text[i] === '}' && --depth === 0) return i + 1
  }
  return text.length
}

/** The paper's \title as plain text, or null. Mirrors manuscript_blueprint.latex_title in the backend. */
export function latexTitle(tex: string): string | null {
  const text = tex.replace(/(?<!\\)%.*/g, (m) => ' '.repeat(m.length)) // comments blanked, same length
  const m = TITLE.exec(text)
  if (!m) return null
  const end = braceEnd(text, m.index + m[0].length - 1)
  let body = end <= text.length && text[end - 1] === '}' ? text.slice(m.index + m[0].length, end - 1) : ''
  for (let t = THANKS.exec(body); t; t = THANKS.exec(body)) { // footnotes in the title are not part of it
    body = body.slice(0, t.index) + ' ' + body.slice(braceEnd(body, t.index + t[0].length - 1))
  }
  const plain = body.replace(BREAK, ' ').replace(ESCAPED, '$1').replace(LETTERS, '').replace(/[{}]/g, '')
  return plain.split(/\s+/).filter(Boolean).join(' ') || null
}
