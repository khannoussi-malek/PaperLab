const WORDS: Record<string, string> = {
  no_free_pdf: 'No free PDF was found for this paper.',
  paper_has_no_pdf: 'This paper is saved without a PDF; attaching one comes in a later version.',
}

/** A refused request's message: a known API code in words, anything else as it came. */
export const codeInWords = (message: string) => WORDS[message] ?? message
