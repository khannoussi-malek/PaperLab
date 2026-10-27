import { describe, expect, it } from 'vitest'
import { ensurePackages, ownLine, slug, uniqueLabel } from './insertBlock'

const MAIN = '\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}\nHi\n\\end{document}\n'

describe('ensurePackages', () => {
  it('adds only the missing lines, just before \\begin{document}', () => {
    expect(ensurePackages(MAIN, ['booktabs'])).toBe('\\documentclass{article}\n\\usepackage{amsmath}\n\\usepackage{booktabs}\n\\begin{document}\nHi\n\\end{document}\n')
  })

  it('puts the compat setting right after pgfplots', () => {
    expect(ensurePackages(MAIN, ['pgfplots', 'graphicx'])).toContain('\\usepackage{pgfplots}\n\\pgfplotsset{compat=1.18}\n\\usepackage{graphicx}\n\\begin{document}')
  })

  it('adds nothing twice: lists, options and a second call', () => {
    const main = '\\documentclass{article}\n\\usepackage[table]{xcolor}\n\\usepackage{graphicx, booktabs}\n\\begin{document}\n\\end{document}'
    expect(ensurePackages(main, ['booktabs', 'graphicx'])).toBeNull()
    const once = ensurePackages(MAIN, ['pgfplots'])!
    expect(ensurePackages(once, ['pgfplots'])).toBeNull()
  })

  it('does not count a commented-out package as loaded', () => {
    const main = '% \\usepackage{booktabs}\n\\begin{document}\n\\end{document}'
    expect(ensurePackages(main, ['booktabs'])).toBe('% \\usepackage{booktabs}\n\\usepackage{booktabs}\n\\begin{document}\n\\end{document}')
  })

  it('says so when there is no \\begin{document}', () => {
    expect(() => ensurePackages('\\usepackage{a}', ['booktabs'])).toThrow('begin{document}')
  })
})

describe('labels', () => {
  it('slugs a name', () => {
    expect(slug('F1 by System (BERT)!')).toBe('f1-by-system-bert')
    expect(slug('???')).toBe('untitled')
  })

  it('numbers a label that exists in any text: inserting twice gives -2, then -3', () => {
    expect(uniqueLabel(['\\section{A}'], 'tab:f1')).toBe('tab:f1')
    const once = '\\label{tab:f1}'
    expect(uniqueLabel([once], 'tab:f1')).toBe('tab:f1-2')
    expect(uniqueLabel(['x', `${once}\n\\label{tab:f1-2}`], 'tab:f1')).toBe('tab:f1-3')
  })
})

describe('ownLine', () => {
  it('breaks before unless at a line start and after unless at a line end', () => {
    expect(ownLine('B', true, true)).toBe('B')
    expect(ownLine('B', false, false)).toBe('\nB\n')
    expect(ownLine('B', true, false)).toBe('B\n')
    expect(ownLine('B', false, true)).toBe('\nB')
  })
})
