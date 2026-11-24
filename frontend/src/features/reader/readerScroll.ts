/** The reader's one scroll path: notes, hovered highlights and cited chunks are all brought into view with it. */
export function scrollToElement(selector: string, block: ScrollLogicalPosition) {
  document.querySelector(selector)?.scrollIntoView({ behavior: 'smooth', block })
}

/** A replaced citation (M33) has no passage box left, so it brings its page to the top instead. */
export const scrollToPage = (page: number) => scrollToElement(`[data-page="${page}"]`, 'start')
