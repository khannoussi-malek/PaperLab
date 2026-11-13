import type { Role } from '@/api/client'

/**
 * What a reader looks for in each kind of section (D180): the IMRaD guide the owner follows, flipped from the author's
 * view to the reader's, in PaperLab's own words. A fixed table: no model writes or judges anything here (D118); it
 * only prompts the reader's own reading. Roles with nothing to check (back matter, other) have no list.
 */
export const READER_CHECKLISTS: Partial<Record<Role, readonly string[]>> = {
  abstract: [
    'Can you say in one sentence what problem the paper tackles?',
    'What do they claim to have found, and is there a number behind it?',
    'Is it clear what kind of study this is: a method, an experiment, a survey, a case study?',
  ],
  intro: [
    'What gap do they say earlier work leaves open?',
    'What exactly do they promise to contribute? Write the contributions down.',
    'Is the problem worth solving for your own question?',
  ],
  related: [
    'Which earlier papers do they build on, and which do they argue against?',
    'Is any work you know of missing from their comparison?',
    'Does their account of what is new hold up against what they cite?',
  ],
  method: [
    'Could you repeat what they did from this description alone?',
    'What data, participants or materials did they use, and how were they chosen?',
    'What are they comparing against, and is that comparison fair?',
    'Which choices look arbitrary, and do they say why they made them?',
  ],
  results: [
    'Do the results answer the question the introduction asked?',
    'How large are the effects, and is the spread or uncertainty reported?',
    'Do the tables and figures say the same thing as the text?',
    'Is anything promised in the method missing from the results?',
  ],
  discussion: [
    'Do they explain the results, or only repeat them?',
    'Do their conclusions go further than the results allow?',
    'How do they square their findings with earlier work that disagrees?',
  ],
  limitations: [
    'Which limits do they admit, and which do they leave out?',
    'Would any of these limits change how far you trust the main result?',
    'How far does the result travel: other data, settings or populations?',
  ],
  conclusion: [
    'Does the conclusion match what the results showed?',
    'What do they say is next, and does it follow from the work?',
    'What will you take from this paper into your own notes?',
  ],
}
