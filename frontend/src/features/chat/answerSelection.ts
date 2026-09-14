/** A selection inside one saved answer: character offsets into its text, and where to float the save button. */
export type AnswerSelection = { outputId: string; anchor: number; focus: number; rect: DOMRect }

const answerTextOf = (node: Node) =>
  (node instanceof Element ? node : node.parentElement)?.closest<HTMLElement>('.chat-answer-text') ?? null

/** Characters from the start of `root`'s text to a boundary point. Works whatever node the boundary is in. */
function offsetIn(root: HTMLElement, node: Node, offset: number): number {
  const range = document.createRange()
  range.selectNodeContents(root)
  range.setEnd(node, offset)
  return range.toString().length
}

/** Reads the browser selection; null unless it lies within the text of a single saved answer. */
export function readAnswerSelection(): AnswerSelection | null {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null
  const range = selection.getRangeAt(0)
  const root = answerTextOf(range.startContainer)
  const outputId = root?.closest<HTMLElement>('[data-output-id]')?.dataset.outputId
  if (!root || !outputId || answerTextOf(range.endContainer) !== root) return null
  return {
    outputId,
    anchor: offsetIn(root, range.startContainer, range.startOffset),
    focus: offsetIn(root, range.endContainer, range.endOffset),
    rect: range.getBoundingClientRect(),
  }
}
