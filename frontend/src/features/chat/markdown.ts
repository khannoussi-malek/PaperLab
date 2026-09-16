import type { Nodes, Parents } from 'mdast'
import { fromMarkdown } from 'mdast-util-from-markdown'
import { gfmFromMarkdown } from 'mdast-util-gfm'
import { gfm } from 'micromark-extension-gfm'
import { MARKER } from './citations'

export type Tag =
  | 'p' | 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6' | 'blockquote' | 'ul' | 'ol' | 'li' | 'hr' | 'pre' | 'code'
  | 'em' | 'strong' | 'del' | 'a' | 'span' | 'table' | 'thead' | 'tbody' | 'tr' | 'th' | 'td'

/**
 * A rendered answer. `text` is shown, `hidden` is markdown syntax (`**`, `- `, `## `, the blank line after a block).
 * Every character of the answer is in exactly one text or hidden piece, in order, so the answer element's text is
 * still the answer itself: Save as note maps selection offsets in it straight onto the saved content (promote.ts).
 */
export type Piece =
  | { kind: 'text' | 'hidden'; text: string }
  | { kind: 'element'; tag: Tag; children: Piece[]; href?: string; start?: number }

const TAGS: Partial<Record<Nodes['type'], Tag>> = {
  paragraph: 'p', blockquote: 'blockquote', listItem: 'li', emphasis: 'em', strong: 'strong', delete: 'del',
  tableRow: 'tr', tableCell: 'td',
}

const SAFE_URL = /^(https?:|mailto:)/i

export function markdownPieces(content: string): Piece[] {
  // A citation marker must never parse as a link or a definition: swap its brackets for same-length inert characters.
  const masked = content.replace(MARKER, (marker) => `\uE000${marker.slice(1, -1)}\uE001`)
  const root = fromMarkdown(masked, { extensions: [gfm()], mdastExtensions: [gfmFromMarkdown()] })

  const slice = (kind: 'text' | 'hidden', from: number, to: number): Piece[] =>
    to > from ? [{ kind, text: content.slice(from, to) }] : []
  const element = (tag: Tag, children: Piece[], extra?: { href?: string; start?: number }): Piece => ({
    kind: 'element', tag, children, ...extra,
  })
  /** Shows `start`..`end` and hides what surrounds it up to `from`..`to`. */
  const shown = (from: number, start: number, end: number, to: number): Piece[] => [
    ...slice('hidden', from, start), ...slice('text', start, end), ...slice('hidden', end, to),
  ]
  const startOf = (node: Nodes) => node.position!.start.offset!
  const endOf = (node: Nodes) => node.position!.end.offset!

  /** A node's children, each owning the syntax before its first child and the gap up to the next one. */
  const childrenOf = (node: Parents, from: number, to: number): Piece[] =>
    node.children.length === 0
      ? slice('hidden', from, to)
      : node.children.flatMap((child, i, all) =>
          build(child, i === 0 ? from : startOf(child), i === all.length - 1 ? to : startOf(all[i + 1])),
        )

  /** Code shows its value and hides the backticks or fences around it; if the value isn't there verbatim, all of it. */
  const code = (value: string, block: boolean, from: number, to: number, start: number, end: number): Piece[] => {
    const lineEnd = content.indexOf('\n', start)
    // A fence's code starts on the next line, so a value that repeats the info string isn't found in it.
    const searchFrom = block && /[`~]/.test(content[start]) ? (lineEnd === -1 ? end : lineEnd + 1) : start
    const at = content.indexOf(value, searchFrom)
    // ponytail: multi-line code indented inside a list loses its indent in `value`, so it shows raw with its fences.
    return at === -1 || at + value.length > end ? shown(from, start, end, to) : shown(from, at, at + value.length, to)
  }

  /** `from`..`to` is the node's own span plus the syntax and whitespace around it that its parent handed down. */
  function build(node: Nodes, from: number, to: number): Piece[] {
    const start = startOf(node)
    const end = endOf(node)
    switch (node.type) {
      case 'text':
        return shown(from, start, end, to)
      case 'inlineCode':
        return [element('code', code(node.value, false, from, to, start, end))]
      case 'code':
        return [element('pre', [element('code', code(node.value, true, from, to, start, end))])]
      case 'thematicBreak':
        return [...slice('hidden', from, to), element('hr', [])]
      case 'heading':
        return [element(`h${node.depth}`, childrenOf(node, from, to))]
      case 'list':
        return [element(node.ordered ? 'ol' : 'ul', childrenOf(node, from, to), node.ordered ? { start: node.start ?? 1 } : {})]
      case 'link':
        return [SAFE_URL.test(node.url) ? element('a', childrenOf(node, from, to), { href: node.url }) : element('span', childrenOf(node, from, to))]
      case 'table': {
        const [head, ...body] = childrenOf(node, from, to)
        const headCells = head.kind === 'element' ? { ...head, children: head.children.map((cell) => (cell.kind === 'element' ? { ...cell, tag: 'th' as const } : cell)) } : head
        return [element('table', [element('thead', [headCells]), ...(body.length ? [element('tbody', body)] : [])])]
      }
    }
    const tag = TAGS[node.type]
    // Anything else (raw HTML, a hard break, an image, a footnote) shows as the text it was written as.
    if (!tag || !('children' in node)) return shown(from, start, end, to)
    return [element(tag, childrenOf(node, from, to))]
  }

  return childrenOf(root, 0, content.length)
}
