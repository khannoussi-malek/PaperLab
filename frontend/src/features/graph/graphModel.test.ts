import { describe, expect, it } from 'vitest'
import type { GraphLink, GraphNode } from '@/api/client'
import {
  countsLine,
  DEFAULT_LAYERS,
  degrees,
  focusedIds,
  KIND_LABELS,
  labelError,
  layerCounts,
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
})

describe('colours', () => {
  it('gives each workspace its own colour, by the first workspace a paper is in', () => {
    const colors = workspaceColors([node('a', ['Thesis']), node('b', ['Reading', 'Thesis']), node('c')], 'light')
    // Alphabetical, and only a paper's *first* workspace counts, so 'Thesis' as b's second does not take a colour twice.
    expect(colors.get('Reading')).toBe('#2a78d6')
    expect(colors.get('Thesis')).toBe('#eb6834')
    expect(colors.size).toBe(2)
  })

  it('orders workspaces by name, so a colour does not move when a paper is added', () => {
    const one = workspaceColors([node('a', ['Zeta']), node('b', ['Alpha'])], 'light')
    const two = workspaceColors([node('b', ['Alpha']), node('a', ['Zeta'])], 'light')
    expect([...one]).toEqual([...two])
    expect(one.get('Alpha')).toBe('#2a78d6')
  })

  it('uses the dark palette in the dark theme and cycles past the sixth workspace', () => {
    const names = ['w1', 'w2', 'w3', 'w4', 'w5', 'w6', 'w7']
    const colors = workspaceColors(names.map((name) => node(name, [name])), 'dark')
    expect(colors.get('w1')).toBe('#3987e5')
    expect(colors.get('w7')).toBe('#3987e5')
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
