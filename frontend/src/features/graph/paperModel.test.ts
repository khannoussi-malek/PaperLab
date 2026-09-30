import { describe, expect, it } from 'vitest'
import type { GraphLink } from '@/api/client'
import { emphasis, labelledIds, LABEL_CAP, linkState, shortTitle } from './paperModel'

const link = (source: string, target: string): GraphLink => ({ source, target, kind: 'cites' })

describe('emphasis', () => {
  it('singles out the selected paper, then the papers around it, and fades the rest', () => {
    const inFocus = new Set(['a', 'b'])
    expect(emphasis('a', 'a', inFocus)).toBe('selected')
    expect(emphasis('b', 'a', inFocus)).toBe('connected')
    expect(emphasis('c', 'a', inFocus)).toBe('faded')
  })

  it('leaves every paper plain when nothing is selected', () => {
    expect(emphasis('a', null, null)).toBe('plain')
  })
})

describe('labelledIds', () => {
  it('names the selected paper and the papers it links to directly', () => {
    const links = [link('a', 'b'), link('c', 'a'), link('b', 'd')]
    expect(labelledIds(links, 'a')).toEqual(new Set(['a', 'b', 'c']))
  })

  it('names nothing when no paper is selected', () => {
    expect(labelledIds([link('a', 'b')], null)).toEqual(new Set())
  })

  it('keeps to a readable number of names around a busy paper, the selected one always first', () => {
    const links = Array.from({ length: 30 }, (_, i) => link('hub', `p${i}`))
    const ids = labelledIds(links, 'hub')
    expect(ids.size).toBe(LABEL_CAP)
    expect(ids.has('hub')).toBe(true)
  })
})

describe('shortTitle', () => {
  it('keeps a short title whole and cuts a long one at a word, with an ellipsis', () => {
    expect(shortTitle('BERT')).toBe('BERT')
    const cut = shortTitle('Homogenization Effects of Large Language Models on Human Creative Ideation')
    expect(cut.endsWith('…')).toBe(true)
    expect(cut.length).toBeLessThanOrEqual(43)
    expect(cut).toBe('Homogenization Effects of Large Language…')
  })
})

describe('linkState', () => {
  const inFocus = new Set(['a', 'b', 'c'])

  it('marks the links of the selected paper as active, either way round', () => {
    expect(linkState(link('a', 'b'), 'a', inFocus)).toBe('active')
    expect(linkState(link('c', 'a'), 'a', inFocus)).toBe('active')
  })

  it('keeps other links inside the focus plain, and fades the ones outside it', () => {
    expect(linkState(link('b', 'c'), 'a', inFocus)).toBe('plain')
    expect(linkState(link('b', 'z'), 'a', inFocus)).toBe('faded')
  })

  it('leaves every link plain when nothing is selected', () => {
    expect(linkState(link('a', 'b'), null, null)).toBe('plain')
  })
})
