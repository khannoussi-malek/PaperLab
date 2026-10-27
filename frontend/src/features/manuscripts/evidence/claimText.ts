import { sentenceAt } from '../pdfEdit'

const COMMENT = /(?<!\\)%.*$/gm
const BLANK_LINE = /\r?\n[ \t]*\r?\n/g
const DROPPED = /\\(?:[a-zA-Z]*cite[a-zA-Z]*|ref|eqref|label|chapter|section|subsection|subsubsection|paragraph)\*?(?:\[[^\]]*\])*\{[^{}]*\}/g
const WITH_ARG = /\\[a-zA-Z]+\*?(?:\[[^\]]*\])*\{([^{}]*)\}/g

/** LaTeX source of one sentence as the plain text a reader (or a model) would see. */
function toPlain(tex: string): string {
  let s = tex
    .replace(COMMENT, '')
    .replace(DROPPED, '')
    .replace(/\\(?:begin|end)\{[^{}]*\}/g, '')
    .replace(/\\\$/g, '\u0000') // an escaped dollar is text, not math
    .replace(/\\\\/g, ' ') // a LaTeX line break, before the command strip reads `\\bc` as `\bc`
  for (let prev = ''; prev !== s; ) {
    prev = s
    s = s.replace(WITH_ARG, '$1') // innermost first, so nested commands unwrap in passes
  }
  return s
    .replace(/\\[a-zA-Z]+\*?/g, '')
    .replace(/\\,/g, ' ')
    .replace(/\\([%&_#])/g, '$1')
    .replace(/\$([^$]*)\$/g, '$1')
    .replace(/\u0000/g, '$')
    .replace(/~/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/** The selection, or else the sentence around the cursor (within its paragraph), with its plain-text form. */
export function sentenceAtCursor(
  doc: string,
  from: number,
  to: number,
): { text: string; plain: string } | null {
  let text: string
  if (from !== to) {
    text = doc.slice(Math.min(from, to), Math.max(from, to))
  } else {
    let start = 0
    let stop = doc.length
    for (const m of doc.matchAll(BLANK_LINE)) {
      if (m.index + m[0].length <= from) start = m.index + m[0].length
      else if (m.index >= from) {
        stop = m.index
        break
      }
    }
    // comments become spaces of the same length, so a full stop inside one splits nothing and offsets stay valid
    const para = doc.slice(start, stop).replace(COMMENT, (c) => ' '.repeat(c.length))
    const span = sentenceAt(para, from - start)
    text = doc.slice(start + span.start, start + span.end)
  }
  text = text.trim()
  const plain = toPlain(text)
  return plain ? { text, plain } : null
}
