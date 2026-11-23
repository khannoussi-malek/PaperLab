import { describe, expect, it } from 'vitest'
import { looksPerPaper } from './eachPaperHint'

describe('looksPerPaper', () => {
  it.each([
    'How does each paper measure adherence?',
    'Compare the EU and US labels and the trial evidence.',
    'Which papers report a sample size?',
    'What do all these studies assume?',
    'How is fatigue defined across the papers?',
  ])('suggests asking each paper for "%s"', (question) => expect(looksPerPaper(question)).toBe(true))

  it.each(['What does Smith mean by construct validity?', 'Summarise the method', 'Why does it fail?'])(
    'stays quiet for "%s"',
    (question) => expect(looksPerPaper(question)).toBe(false),
  )
})
