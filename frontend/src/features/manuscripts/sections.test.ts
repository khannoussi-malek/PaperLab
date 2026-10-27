import { describe, expect, it } from 'vitest'
import { sectionRows, sectionText, wordCount } from './sections'

const MAIN = '\\begin{document}\n\\input{sections/intro}\n\\clearpage\n\\input{sections/method.tex}\n% \\input{sections/old}\n\\bibliography{paperlab}\n\\end{document}\n'

describe('sectionRows', () => {
  it('reads input and include in every written form', () => {
    const files = { 'sections/intro.tex': '\\section{Intro}\nHi', 'sections/method.tex': 'no heading' }
    const rows = sectionRows({ ...files, 'main.tex': MAIN }, 'main.tex')
    expect(rows).toEqual([
      { path: 'sections/intro.tex', title: 'Intro', line: 2, inMain: false, missing: false },
      { path: 'sections/method.tex', title: 'method', line: 4, inMain: false, missing: false },
    ])
  })
  it('handles spaces, include, comments, escaped percent, two per line and brace-less input', () => {
    const rows = (t: string) => sectionRows({ 'main.tex': t }, 'main.tex').map((r) => r.path)
    expect(rows('\\input{ a }\\include{b}\n')).toEqual(['a.tex', 'b.tex'])
    expect(rows('\\input {sections/x}\n')).toEqual(['sections/x.tex'])
    expect(rows('\\input sections/x\n')).toEqual([])
    expect(rows('\\input{a} % \\input{b}\n100\\% \\input{c}\n')).toEqual(['a.tex', 'c.tex'])
  })
  it('counts only body inputs before the first end marker (same case as the backend)', () => {
    const PRE = '\\documentclass{article}\n\\input{macros}\n\\bibliographystyle{plain}\n\\begin{document}\n\\input{sections/a}\n\\input{sections/b}\n\\appendix\n\\input{sections/app}\n\\bibliography{x}\n\\end{document}\n'
    const rows = (t: string) => sectionRows({ 'main.tex': t }, 'main.tex').map((r) => r.path)
    expect(rows(PRE)).toEqual(['sections/a.tex', 'sections/b.tex'])
    expect(rows('\\input{a}\n\\bibliography{x}\n\\input{b}\n')).toEqual(['a.tex', 'b.tex']) // no \begin{document}: all
    const single = '\\input{macros}\n\\begin{document}\n\\section{One}\nx\n\\end{document}\n'
    expect(sectionRows({ 'main.tex': single }, 'main.tex')).toEqual([{ path: 'main.tex', title: 'One', line: 3, inMain: true, missing: false }])
  })
  it('marks a missing file instead of crashing', () => {
    const [row] = sectionRows({ 'main.tex': '\\input{sections/gone}' }, 'main.tex')
    expect(row).toMatchObject({ path: 'sections/gone.tex', title: 'gone', missing: true })
  })
  it('falls back to top-level sections of main', () => {
    const main = 'a\n\\section{One}\nx\n\\subsection{Sub}\ny\n\\section*{Two}\nz\n\\end{document}\n'
    const rows = sectionRows({ 'main.tex': main }, 'main.tex')
    expect(rows).toEqual([
      { path: 'main.tex', title: 'One', line: 2, inMain: true, missing: false },
      { path: 'main.tex', title: 'Two', line: 6, inMain: true, missing: false },
    ])
    expect(sectionText({ 'main.tex': main }, rows[0])).toBe('\\section{One}\nx\n\\subsection{Sub}\ny')
    expect(sectionText({ 'main.tex': main }, rows[1])).toBe('\\section*{Two}\nz')
  })
  it('reads \section with a space before the brace', () => {
    expect(sectionRows({ 'main.tex': '\\section {Spaced}' }, 'main.tex')[0].title).toBe('Spaced')
  })
  it('ends an in-main section at bibliography and appendix markers', () => {
    for (const end of ['\\bibliographystyle{x}', '\\bibliography{x}', '\\printbibliography', '\\appendix', '\\end{document}', 'ok % \\appendix\nmore']) {
      const main = `\\section{A}\nbody\n${end}\nafter`
      const [row] = sectionRows({ 'main.tex': main }, 'main.tex')
      expect(sectionText({ 'main.tex': main }, row)).toBe(end.includes('%') ? `\\section{A}\nbody\n${end}\nafter` : '\\section{A}\nbody')
    }
  })
  it('sectionText returns the whole file for a file row, empty for a missing one', () => {
    const files = { 'main.tex': '\\input{s/a}\\input{s/b}', 's/a.tex': 'AAA' }
    const [a, b] = sectionRows(files, 'main.tex')
    expect(sectionText(files, a)).toBe('AAA')
    expect(sectionText(files, b)).toBe('')
  })
})

describe('wordCount', () => {
  it('ignores comments, commands, math and equation bodies but counts \\emph text', () => {
    const tex = [
      'One \\emph{two three} four % ignored words here',
      'Math $x + y$ and \\[ a b c \\] end 100\\% sure',
      '\\begin{equation}\n e = mc \n\\end{equation}',
      '\\begin{align*} p q r \\end{align*}',
      '\\cite{smith2020}',
    ].join('\n')
    // One two three four Math and end 100 sure
    expect(wordCount(tex)).toBe(9)
    expect(wordCount('')).toBe(0)
  })
})
