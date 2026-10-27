import { sentenceAt } from '../pdfEdit'

const COMMENT = /(?<!\\)%.*$/gm
const DROPPED = /\\(?:[a-zA-Z]*cite[a-zA-Z]*|ref|eqref|label)\*?(?:\[[^\]]*\])*\{[^{}]*\}/g
const WITH_ARG = /\\[a-zA-Z]+\*?(?:\[[^\]]*\])*\{([^{}]*)\}/g

/** LaTeX source of one sentence as the plain text a reader (or a model) would see. */
function toPlain(tex: string): string {
  let s = tex.replace(COMMENT, '').replace(DROPPED, '')
  for (let prev = ''; prev !== s; ) {
    prev = s
    s = s.replace(WITH_ARG, '$1') // innermost first, so nested commands unwrap in passes
  }
  return s
    .replace(/\\[a-zA-Z]+\*?/g, '')
    .replace(/\\%/g, '%')
    .replace(/\$([^$]*)\$/g, '$1')
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
    const before = doc.slice(0, from)
    const gap = before.lastIndexOf('\n\n')
    const start = gap < 0 ? 0 : gap + 2
    const stop = doc.indexOf('\n\n', from)
    const para = doc.slice(start, stop < 0 ? doc.length : stop)
    const span = sentenceAt(para, from - start)
    text = para.slice(span.start, span.end)
  }
  text = text.trim()
  const plain = toPlain(text)
  return plain ? { text, plain } : null
}
