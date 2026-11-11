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
