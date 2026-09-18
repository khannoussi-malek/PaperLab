import { describe, expect, it } from 'vitest'
import type { GraphLink, GraphNode } from '@/api/client'
import { sequentialScale } from '@/features/charts/palette'
import { DIAGONAL, kindsText, matrix, MATRIX_CAP, MATRIX_CAP_LINE, MATRIX_CAPTION } from './matrixModel'

const link = (source: string, target: string, kind: GraphLink['kind']): GraphLink => ({
  source,
  target,
  kind,
  id: null,
  label: null,
})

const node = (id: string, title: string, workspaces: string[] = []): GraphNode => ({
  id,
  title,
  year: null,
  workspaces,
  has_notes: false,
  status: 'ready',
  added_at: '2026-09-13T10:00:00Z',
})

describe('the matrix', () => {
  it('groups papers by first workspace (unfiled last), then by link count, then title', () => {
    const nodes = [
      node('u', 'Unfiled'),
      node('t1', 'Zeta', ['Thesis']),
      node('t2', 'Alpha', ['Thesis']),
      node('r1', 'Busy', ['Reading']),
      node('r2', 'Quiet', ['Reading', 'Thesis']),
    ]
    // Links: Busy 2, Zeta 2, Unfiled 2, Quiet 1, Alpha 1.
    const links = [link('r1', 't1', 'cites'), link('r1', 'u', 'similar'), link('t1', 'u', 'similar'), link('r2', 't2', 'similar')]
    expect(matrix(nodes, links, 'light').papers.map((paper) => paper.title)).toEqual([
      'Busy',
      'Quiet',
      'Zeta',
      'Alpha',
      'Unfiled',
    ])
  })

  it('keeps the 50 most connected papers, ties broken by title, and says it cut', () => {
    const nodes = Array.from({ length: 52 }, (_, n) => node(`p${n}`, `Paper ${String(n).padStart(2, '0')}`))
    const result = matrix(nodes, [link('p50', 'p51', 'cites')], 'light')
    const titles = result.papers.map((paper) => paper.title)
    expect(MATRIX_CAP).toBe(50)
    expect(titles).toHaveLength(50)
    // The two linked papers first, then the unlinked ones by title: Paper 48 and Paper 49 are the ones left out.
    expect(titles.slice(0, 3)).toEqual(['Paper 50', 'Paper 51', 'Paper 00'])
    expect(titles).not.toContain('Paper 48')
    expect(titles).not.toContain('Paper 49')
    expect(result.capped).toBe(true)
    expect(MATRIX_CAP_LINE).toBe('Showing the 50 most connected papers.')
    expect(matrix(nodes.slice(0, 50), [], 'light').capped).toBe(false)
  })

  it('names a linked cell by both titles and every kind joining them, shaded by how many kinds', () => {
    const nodes = [node('a', 'Attention'), node('b', 'BERT'), node('c', 'CLIP')]
    const links = [link('a', 'b', 'similar'), link('b', 'a', 'cites'), link('a', 'c', 'manual')]
    const { papers, cells } = matrix(nodes, links, 'dark')
    expect(papers.map((paper) => paper.id)).toEqual(['a', 'b', 'c'])
    expect(cells[0][1]).toEqual({
      kinds: ['cites', 'similar'],
      name: 'Attention and BERT: Citations, similar content',
      color: sequentialScale('dark')[1][1],
    })
    expect(cells[1][0]?.name).toBe('BERT and Attention: Citations, similar content')
    expect(cells[0][2]).toEqual({
      kinds: ['manual'],
      name: 'Attention and CLIP: Your links',
      color: sequentialScale('dark')[0][1],
    })
    expect(cells[1][2]).toBeNull()
  })

  it('leaves the diagonal without a link, reading —, under the table’s caption', () => {
    const { cells } = matrix([node('a', 'A'), node('b', 'B')], [link('a', 'b', 'cites')], 'light')
    expect([cells[0][0], cells[1][1]]).toEqual([null, null])
    expect(DIAGONAL).toBe('—')
    expect(MATRIX_CAPTION).toBe('Links between your papers')
  })

  it('writes the kinds lowercase after the first, in the controls’ order', () => {
    expect(kindsText(['cites', 'same_workspace', 'manual'])).toBe('Citations, same workspace, your links')
  })
})
