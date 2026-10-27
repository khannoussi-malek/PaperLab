import { expect, test } from 'vitest'
import { jumpTargets } from './jumpTargets'
import { outline } from './outline'
import { sectionRows } from './sections'

const texts = {
  'main.tex': '\\section{Intro}\n\\label{sec:intro}\n% \\label{sec:gone}\n\\input{b}',
  'b.tex': '\\section{Methods}\n\\subsection{Data}\nx \\label{tab:data}',
}
const paper = { paper_id: 'pk', key: 'k1', pinned: false, title: 'Kappa paper', first_author: 'Kappa', year: 2021, has_pdf: true, notes: 0, highlights: 0, ai_notes: 0 }

test('targets: sections, headings, uncommented labels with file and line, papers', () => {
  const rows = sectionRows(texts, 'main.tex')
  const t = jumpTargets(rows, outline(texts, 'main.tex'), texts, [paper])
  expect(t.filter((x) => x.kind === 'section').map((x) => x.label)).toEqual(['Methods'])
  expect(t.filter((x) => x.kind === 'heading').map((x) => x.label)).toEqual(['Intro', 'Data']) // Methods is already a section
  expect(t.find((x) => x.label === 'Data')).toMatchObject({ file: 'b.tex', line: 2 })
  expect(t.filter((x) => x.kind === 'label')).toEqual([
    expect.objectContaining({ label: 'sec:intro', file: 'main.tex', line: 2, detail: 'Intro (main.tex)' }),
    expect.objectContaining({ label: 'tab:data', file: 'b.tex', line: 3, detail: 'Data (b.tex)' }),
  ])
  expect(t.find((x) => x.kind === 'paper')).toMatchObject({ key: 'k1', label: 'Kappa paper', detail: 'Kappa 2021' })
})
