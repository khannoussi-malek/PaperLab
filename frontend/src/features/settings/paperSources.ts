import type { PaperSourceId } from '@/api/client'

/** What each source is for, under its switch in Settings → Paper sources. */
export const DESCRIPTIONS: Record<PaperSourceId, string> = {
  openalex: 'Title and DOI search, and details for the papers you upload.',
  crossref: 'Title and DOI search across papers with a DOI. Free.',
  semantic_scholar: 'Similar papers, arXiv lookups and free PDF links. Free; a free key avoids its busy shared pool.',
  arxiv: 'arXiv preprints and their PDFs. Free.',
  core: 'Open-access papers from university repositories, with PDFs. Free; a free key raises its limit.',
  unpaywall: 'Free, legal PDF links for papers with a DOI. Free; needs the contact email.',
}

export const OPENALEX_PRICE =
  'Free up to $0.10 of use a day without a key, or $1 a day with a free key from openalex.org. More needs a paid plan there.'

// The server's rule for the contact email (core/paper_sources.py), so a typo is caught before it is sent.
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const MAX_EMAIL_LENGTH = 254
const EMAIL_PROBLEM = 'Enter an email address like name@example.org.'

/**
 * Why the server would refuse `text` as the contact email, in its words, or null when it would be saved. Blank text
 * is not a problem: it saves nothing (Save stays disabled), and Remove is how an email is cleared.
 */
export function emailProblem(text: string): string | null {
  const email = text.trim()
  if (email === '') return null
  // Counted in characters like Python's len(), not UTF-16 units.
  return EMAIL.test(email) && [...email].length <= MAX_EMAIL_LENGTH ? null : EMAIL_PROBLEM
}

/** "Key ending in T123", or "Key saved" for a key too short to hint (the server sends no hint for keys under 8). */
export const keyLine = (hint: string | null): string => (hint ? `Key ending in ${hint}` : 'Key saved')
