import { expect, test } from 'vitest'
import { outline } from './outline'

test('reads sections in order', () => {
  const files = { 'main.tex': '\\section{Intro}\ntext\n\\subsection{Aim}\n\\subsubsection{Detail}\n\\section{End}' }
  expect(outline(files, 'main.tex')).toEqual([
    { level: 1, title: 'Intro', file: 'main.tex', line: 1 },
    { level: 2, title: 'Aim', file: 'main.tex', line: 3 },
    { level: 3, title: 'Detail', file: 'main.tex', line: 4 },
    { level: 1, title: 'End', file: 'main.tex', line: 5 },
  ])
})

test('follows input once', () => {
  const files = {
    'main.tex': '\\section{A}\n\\input{sec/b}\n\\include{sec/b.tex}\n\\section{C}',
    'sec/b.tex': '\\section{B}',
  }
  expect(outline(files, 'main.tex').map((i) => i.title)).toEqual(['A', 'B', 'C'])
  expect(outline(files, 'main.tex')[1]).toMatchObject({ file: 'sec/b.tex', line: 1 })
})

test('skips commented headings', () => {
  const files = { 'main.tex': '% \\section{Old}\n\\section{New} % \\section{Nope}\n100\\% \\section{Real}' }
  expect(outline(files, 'main.tex').map((i) => i.title)).toEqual(['New', 'Real'])
})

test('starred sections', () => {
  expect(outline({ 'main.tex': '\\section*{Intro}\n\\subsection*{Aim}' }, 'main.tex').map((i) => [i.level, i.title])).toEqual([
    [1, 'Intro'],
    [2, 'Aim'],
  ])
})
