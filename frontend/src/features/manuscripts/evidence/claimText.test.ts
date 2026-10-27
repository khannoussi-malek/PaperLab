import { describe, expect, it } from 'vitest'
import { sentenceAtCursor } from './claimText'

describe('sentenceAtCursor', () => {
  it('takes the selection when it is not empty', () => {
    const doc = 'One. Two words here. Three.'
    expect(sentenceAtCursor(doc, 5, 19)).toEqual({ text: 'Two words here', plain: 'Two words here' })
  })

  it('takes the sentence around the cursor, across lines, inside the paragraph', () => {
    const doc = 'First one.\n\nWe show that\nit works well. Next sentence.\n\nOther.'
    const at = doc.indexOf('works')
    expect(sentenceAtCursor(doc, at, at)?.plain).toBe('We show that it works well.')
  })

  it('does not cross a blank line', () => {
    const doc = 'Alpha beta\n\nGamma delta'
    const at = doc.indexOf('Gamma')
    expect(sentenceAtCursor(doc, at, at)?.plain).toBe('Gamma delta')
  })

  it('strips latex to plain text', () => {
    const doc = String.raw`We use \emph{deep} nets~\citep[see][p.~2]{x} with $a+b$ terms\footnote{} and \ref{fig:1}\label{l} \noindent fine. % a comment. here`
    expect(sentenceAtCursor(doc, 0, 0)?.plain).toBe('We use deep nets with a+b terms and fine.')
  })

  it('keeps an escaped percent as a percent', () => {
    expect(sentenceAtCursor(String.raw`It is 5\% better.`, 0, 0)?.plain).toBe('It is 5% better.')
  })

  it('is null when nothing is left', () => {
    expect(sentenceAtCursor(String.raw`\citep{x} % only`, 0, 0)).toBeNull()
    expect(sentenceAtCursor('', 0, 0)).toBeNull()
  })
})
