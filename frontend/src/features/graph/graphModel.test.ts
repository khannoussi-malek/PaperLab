import { describe, expect, it } from 'vitest'
import type { GraphLink, GraphNode } from '@/api/client'
import {
  carryPositions,
  connectionNote,
  countsLine,
  DEFAULT_LAYERS,
  degrees,
  focusedIds,
  hopDistances,
  hopSections,
  KIND_LABELS,
  labelError,
  layerCounts,
  legendEntries,
  nodeColor,
  sizedNodes,
  tooltipFor,
  visibleLinks,
  workspaceColors,
} from './graphModel'

const link = (source: string, target: string, kind: GraphLink['kind']): GraphLink => ({
  source,
  target,
  kind,
  id: null,
  label: null,
})

const node = (id: string, workspaces: string[] = []): GraphNode => ({
  id,
  title: id.toUpperCase(),
  year: 2020,
  workspaces,
  has_notes: false,
  status: 'ready',
  added_at: '2026-09-13T10:00:00Z',
})

describe('layers', () => {
  const links = [
    link('a', 'b', 'cites'),
    link('b', 'c', 'similar'),
    link('c', 'd', 'similar'),
    link('a', 'd', 'same_workspace'),
  ]

  it('counts every kind, including the ones with none', () => {
    expect(layerCounts(links)).toEqual({
      cites: 1,
      same_workspace: 1,
      co_anchored: 0,
      co_authored: 0,
      shares_topic: 0,
      similar: 2,
      manual: 0,
    })
  })

  it('shows citations and similar content by default', () => {
    expect(DEFAULT_LAYERS).toEqual(['cites', 'similar'])
    expect(visibleLinks(links, DEFAULT_LAYERS)).toHaveLength(3)
  })

  it('keeps only the ticked kinds, and nothing when none is ticked', () => {
    expect(visibleLinks(links, ['same_workspace'])).toEqual([link('a', 'd', 'same_workspace')])
    expect(visibleLinks(links, [])).toEqual([])
  })

  it('labels every kind exactly as the spec words it', () => {
    expect(KIND_LABELS).toEqual({
      cites: 'Citations',
      same_workspace: 'Same workspace',
      co_anchored: 'Noted together',
      co_authored: 'Same author',
      shares_topic: 'Same topic',
      similar: 'Similar content',
      manual: 'Your links',
    })
  })
})

describe('focus', () => {
  // a -> b -> c -> d, and a cycle back from c to a.
  const links = [
    link('a', 'b', 'cites'),
    link('b', 'c', 'cites'),
    link('c', 'd', 'cites'),
    link('c', 'a', 'cites'),
  ]

  it('reaches one, two and three links out, in either direction', () => {
    expect(focusedIds(links, 'a', 1)).toEqual(new Set(['a', 'b', 'c']))
    expect(focusedIds(links, 'a', 2)).toEqual(new Set(['a', 'b', 'c', 'd']))
    expect(focusedIds(links, 'd', 1)).toEqual(new Set(['d', 'c']))
    expect(focusedIds(links, 'd', 2)).toEqual(new Set(['d', 'c', 'b', 'a']))
  })

  it('ends on a cycle instead of looping', () => {
    expect(focusedIds(links, 'a', 3)).toEqual(new Set(['a', 'b', 'c', 'd']))
  })

  it('walks only the visible layers', () => {
    const mixed = [link('a', 'b', 'cites'), link('b', 'c', 'shares_topic')]
    expect(focusedIds(visibleLinks(mixed, ['cites']), 'a', 3)).toEqual(new Set(['a', 'b']))
  })

  it('leaves an unlinked paper on its own', () => {
    expect(focusedIds(links, 'lonely', 3)).toEqual(new Set(['lonely']))
  })

  it('measures how many links away each paper is, up to the limit, in either direction', () => {
    expect(hopDistances(links, 'a', 3)).toEqual(
      new Map([
        ['a', 0],
        ['b', 1],
        ['c', 1],
        ['d', 2],
      ])
    )
    expect(hopDistances(links, 'd', 1)).toEqual(
      new Map([
        ['d', 0],
        ['c', 1],
      ])
    )
  })
})

describe('colours', () => {
  it('colours every workspace from the full list, alphabetically, whatever is on screen', () => {
    const colors = workspaceColors(['Thesis', 'Reading', 'Archive'], 'light')
    expect([...colors]).toEqual([
      ['Archive', '#2a78d6'],
      ['Reading', '#eb6834'],
      ['Thesis', '#1baf7a'],
    ])
    // The page passes every workspace, not the papers' own: filtering to one workspace can't move its colour.
    expect(workspaceColors(['Reading', 'Archive', 'Thesis'], 'light')).toEqual(colors)
  })

  it('uses the dark palette in the dark theme and cycles past the sixth workspace', () => {
    const colors = workspaceColors(['w1', 'w2', 'w3', 'w4', 'w5', 'w6', 'w7'], 'dark')
    expect(colors.get('w1')).toBe('#3987e5')
    expect(colors.get('w7')).toBe('#3987e5')
  })

  it('paints a paper by its first workspace, and an unfiled one in the muted ink', () => {
    const colors = workspaceColors(['Reading', 'Thesis'], 'light')
    expect(nodeColor(node('a', ['Thesis', 'Reading']), colors, 'light')).toBe('#eb6834')
    expect(nodeColor(node('b'), colors, 'dark')).toBe('#94a3b8')
  })
})

describe('the legend', () => {
  const colors = workspaceColors(['Archive', 'Reading', 'Thesis'], 'light')

  it('names only the workspaces that colour a paper on screen', () => {
    // 'Thesis' is only b's second workspace, so it colours nothing here, and no paper here is in 'Archive'.
    expect(legendEntries([node('a', ['Reading']), node('b', ['Reading', 'Thesis'])], colors, 'light')).toEqual([
      { name: 'Reading', color: '#eb6834' },
    ])
  })

  it('ends with No workspace, in exactly the colour an unfiled paper wears', () => {
    const entries = legendEntries([node('a', ['Thesis']), node('b')], colors, 'dark')
    expect(entries.map((entry) => entry.name)).toEqual(['Thesis', 'No workspace'])
    expect(entries[1].color).toBe(nodeColor(node('b'), colors, 'dark'))
  })

  it('leaves No workspace out when every paper has one', () => {
    expect(legendEntries([node('a', ['Thesis'])], colors, 'light').map((entry) => entry.name)).toEqual(['Thesis'])
  })
})

describe('degrees', () => {
  it('counts both ends of a link', () => {
    expect(degrees([link('a', 'b', 'cites')])).toEqual(
      new Map([
        ['a', 1],
        ['b', 1],
      ])
    )
  })

  it('leaves a paper with no links out of the map', () => {
    expect(degrees([link('a', 'b', 'cites')]).has('lonely')).toBe(false)
  })

  it('counts a paper twice when two links touch it', () => {
    expect(degrees([link('a', 'b', 'cites'), link('a', 'c', 'similar')]).get('a')).toBe(2)
  })
})

describe('the counts line', () => {
  it('counts the papers and the visible links, with singulars', () => {
    expect(countsLine(2, 3)).toBe('2 papers, 3 links')
    expect(countsLine(1, 1)).toBe('1 paper, 1 link')
    expect(countsLine(0, 0)).toBe('0 papers, 0 links')
  })
})

describe('the node tooltip', () => {
  it('writes untrusted text through textContent only, never innerHTML', () => {
    const writes: { textContent?: string; innerHTML?: string } = {}
    const fakeElement = {
      set textContent(value: string) {
        writes.textContent = value
      },
      set innerHTML(value: string) {
        writes.innerHTML = value
      },
    }
    const fakeDoc = { createElement: () => fakeElement } as unknown as Pick<Document, 'createElement'>

    const result = tooltipFor('<img src=x onerror=alert(1)>', fakeDoc)

    expect(result).toBe(fakeElement)
    expect(writes).toEqual({ textContent: '<img src=x onerror=alert(1)>' })
  })
})

describe('a link label', () => {
  it('accepts a trimmed label of 1 to 80 characters', () => {
    expect(labelError('builds on')).toBeNull()
    expect(labelError('  builds on  ')).toBeNull()
    expect(labelError('x'.repeat(80))).toBeNull()
  })

  it('refuses a blank or over-long label, with the message the API would send', () => {
    expect(labelError('')).toBe('A link needs a short label, like "builds on".')
    expect(labelError('   ')).toBe('A link needs a short label, like "builds on".')
    expect(labelError('x'.repeat(81))).toBe('Keep the label under 80 characters.')
  })
})

describe('the canvas nodes', () => {
  it('sizes a paper from 3 to 9 by its share of the links, and paints it', () => {
    const colors = workspaceColors(['Thesis'], 'light')
    const links = [link('a', 'b', 'cites'), link('a', 'c', 'similar')]
    const sized = sizedNodes([node('a', ['Thesis']), node('b'), node('c')], links, colors, 'light')
    expect(sized.map((paper) => [paper.id, paper.radius, paper.color])).toEqual([
      ['a', 9, '#2a78d6'],
      ['b', 6, '#475569'],
      ['c', 6, '#475569'],
    ])
  })
})

describe('positions across a rebuild', () => {
  it('starts a surviving paper where it was, at rest, and leaves a new one to the simulation', () => {
    const previous = [
      { id: 'a', x: 10, y: -4, vx: 3, vy: 1 },
      { id: 'gone', x: 1, y: 1 },
    ]
    expect(carryPositions([{ id: 'a', title: 'A' }, { id: 'new', title: 'N' }], previous)).toEqual([
      { id: 'a', title: 'A', x: 10, y: -4, vx: 0, vy: 0 },
      { id: 'new', title: 'N' },
    ])
  })

  it('keeps the depth too, in 3D', () => {
    expect(carryPositions([{ id: 'a' }], [{ id: 'a', x: 1, y: 2, z: 3 }])).toEqual([
      { id: 'a', x: 1, y: 2, z: 3, vx: 0, vy: 0, vz: 0 },
    ])
  })

  it('leaves a paper the simulation never placed to be placed, and never edits what it is given', () => {
    const fresh = [{ id: 'a' }]
    expect(carryPositions(fresh, [{ id: 'a' }])).toEqual([{ id: 'a' }])
    carryPositions(fresh, [{ id: 'a', x: 1, y: 2 }])
    expect(fresh).toEqual([{ id: 'a' }])
  })
})

describe('the panel', () => {
  it('says which way a citation or your own link points, with your label after it', () => {
    const cites = link('a', 'b', 'cites')
    const mine = { ...link('a', 'b', 'manual'), id: 'l1', label: 'builds on' }
    expect(connectionNote(cites, 'a')).toBe('this paper cites it')
    expect(connectionNote(cites, 'b')).toBe('it cites this paper')
    expect(connectionNote(mine, 'a')).toBe('your link to it: builds on')
    expect(connectionNote(mine, 'b')).toBe('your link from it: builds on')
    expect(connectionNote(link('a', 'b', 'similar'), 'a')).toBeNull()
  })

  it('lists the papers two and three links away under their own headings, by title', () => {
    // a – b, then b – c and b – z, then c – d: from a, b is 1 away, c and z 2, d 3.
    const nodes = [node('a'), node('b'), node('c'), node('d'), { ...node('z'), title: 'ALPHA' }]
    const links = [link('a', 'b', 'cites'), link('b', 'c', 'similar'), link('b', 'z', 'similar'), link('c', 'd', 'cites')]
    expect(hopSections(nodes, links, 'a', 3)).toEqual([
      { heading: '2 links away', papers: [nodes[4], nodes[2]] },
      { heading: '3 links away', papers: [nodes[3]] },
    ])
    expect(hopSections(nodes, links, 'a', 2).map((section) => section.heading)).toEqual(['2 links away'])
    expect(hopSections(nodes, links, 'a', 1)).toEqual([])
  })
})
