const WORDS: Record<string, string> = {
  no_free_pdf: 'No free PDF was found for this paper.',
  already_has_pdf: 'This paper already has its PDF.',
  needs_full_text: 'Needs the full text to assess.',
  not_a_pdf: 'That file is not a PDF.',
  pdf_too_large: 'That PDF is larger than 30 MB.',
}

/** A refused request's message: a known API code in words, anything else as it came. */
export const codeInWords = (message: string) => WORDS[message] ?? message

const OUTCOMES: Record<string, string> = {
  not_a_pdf: 'it was not a PDF',
  bot_check: 'the site asked for a human check',
  too_large: 'the file was too large',
  unsafe_url: 'the address was not safe to open',
  busy: 'the site was busy',
  no_match: 'no matching copy',
  in_library: 'already in your library',
  pdf: 'a PDF',
}

/** One `tried` outcome from a failed find, in plain words: known codes, `http_<status>`, and anything else as it came. */
export function outcomeInWords(outcome: string): string {
  if (OUTCOMES[outcome]) return OUTCOMES[outcome]
  const status = /^http_(\d+)$/.exec(outcome)
  if (status) return `the site answered ${status[1]}`
  if (outcome.startsWith('not_a_pdf →')) return 'it was a web page, so its declared PDF link was tried too'
  return outcome.startsWith('error: ') ? "the site couldn't be reached" : outcome
}
