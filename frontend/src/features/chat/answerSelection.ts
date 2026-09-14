/** A selection inside one saved answer: character offsets into its text, and where to float the save button. */
export type AnswerSelection = { outputId: string; anchor: number; focus: number; rect: DOMRect }

const elementOf = (node: Node) => (node instanceof Element ? node : node.parentElement)
const closestOf = (node: Node, selector: string) => elementOf(node)?.closest<HTMLElement>(selector) ?? null

/** Characters from the start of `root`'s text to a boundary point. Works whatever node the boundary is in. */
function offsetIn(root: HTMLElement, node: Node, offset: number): number {
  const range = document.createRange()
  range.selectNodeContents(root)
  range.setEnd(node, offset)
  return range.toString().length
}

/**
 * A boundary point that has overshot `root` (a triple-click or a drag ending in the sources list or the footer,
 * still inside the same answer) clamps to whichever end of `root`'s text it landed past, so the body sent to the
 * API is always a slice of the answer's own text.
 */
function clampedOffsetIn(root: HTMLElement, node: Node, offset: number): number {
  if (root.contains(node)) return offsetIn(root, node, offset)
  const precedesRoot = (root.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_PRECEDING) !== 0
  return precedesRoot ? 0 : (root.textContent?.length ?? 0)
}

/** Reads the browser selection; null unless it lies within one saved answer's article, outside its question. */
export function readAnswerSelection(): AnswerSelection | null {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null
  const range = selection.getRangeAt(0)

  const article = closestOf(range.startContainer, 'article[data-output-id]')
  const endArticle = closestOf(range.endContainer, 'article[data-output-id]')
  const outputId = article?.dataset.outputId
  const root = article?.querySelector<HTMLElement>('.chat-answer-text')
  if (!article || article !== endArticle || !outputId || !root) return null
  // The question bubble sits in the same article as its answer, so overshooting into it isn't an anchor overshoot.
  if (closestOf(range.startContainer, '.chat-question') || closestOf(range.endContainer, '.chat-question')) return null

  return {
    outputId,
    anchor: clampedOffsetIn(root, range.startContainer, range.startOffset),
    focus: clampedOffsetIn(root, range.endContainer, range.endOffset),
    rect: range.getBoundingClientRect(),
  }
}
