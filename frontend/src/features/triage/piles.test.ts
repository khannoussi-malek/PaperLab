import { describe, expect, it } from 'vitest'
import { PILES, PILE_ORDER, REASONS, buildDecision, nextState, pileForDrag, pileForKey, type Pile } from './piles'

const clock = { card_ms: 1234, pdf_ms: 0, pdf_opened: false }
const ids = { sessionId: 's1', clientId: 'c1', clock }

describe('nextState', () => {
  const starts: [string | null, number][] = [[null, 0], ['keep', 1], ['drop', 3]]
  const expected: Record<Pile, [string | null, number][]> = {
    read_closely: [['keep', 0], ['keep', 1], ['keep', 3]],
    skim: [['keep', 1], ['keep', 1], ['keep', 3]],
    later: [['later', 0], ['later', 1], ['later', 3]],
    not_relevant: [['drop', 0], ['drop', 1], ['drop', 3]],
    skip: [[null, 0], ['keep', 1], ['drop', 3]],
  }
  for (const pile of PILE_ORDER)
    it(`${pile} from each start`, () => {
      starts.forEach(([t, p], i) => {
        const [triage, pass] = expected[pile][i]
        expect(nextState(pile, t as never, p)).toEqual({ triage, pass })
      })
    })
})

describe('pileForKey', () => {
  it('matches every pile button', () => {
    for (const pile of PILE_ORDER) {
      expect(pileForKey(String(PILES[pile].key))).toBe(pile)
      expect(pileForKey(PILES[pile].arrow)).toBe(pile)
    }
  })
  it('ignores other keys', () => {
    for (const k of ['6', 'a', 'Enter', '0']) expect(pileForKey(k)).toBeNull()
  })
})

describe('pileForDrag', () => {
  it('picks the dominant axis', () => {
    expect(pileForDrag(120, 30)).toBe('read_closely')
    expect(pileForDrag(-120, 30)).toBe('not_relevant')
    expect(pileForDrag(10, 120)).toBe('skim')
    expect(pileForDrag(10, -120)).toBe('later')
  })
  it('is null under 80 px and ties go horizontal', () => {
    expect(pileForDrag(79, 0)).toBeNull()
    expect(pileForDrag(80, 80)).toBe('read_closely')
    expect(pileForDrag(-90, 90)).toBe('not_relevant')
  })
})

describe('buildDecision', () => {
  it('carries integer ms, pdf_opened false and no reason for a non-drop', () => {
    const d = buildDecision({ pile: 'skim', ...ids, clock: { ...clock, card_ms: 1234.7 } })
    expect(d).toMatchObject({ pile: 'skim', session_id: 's1', client_id: 'c1', pdf_opened: false, card_ms: 1235, pdf_ms: 0 })
    expect('reason' in d).toBe(false)
    expect('fivecs' in d).toBe(false)
  })
  it('throws for not_relevant without a reason', () => {
    expect(() => buildDecision({ pile: 'not_relevant', ...ids })).toThrow()
    expect(buildDecision({ pile: 'not_relevant', ...ids, reason: 'off_topic', note: 'x' })).toMatchObject({ reason: 'off_topic', note: 'x' })
  })
})

describe('REASONS', () => {
  it('has as many labels as keys, with the spec wording', () => {
    for (const pile of PILE_ORDER) expect(new Set(REASONS[pile].map((r) => r.label)).size).toBe(REASONS[pile].length)
    expect(REASONS.not_relevant[0]).toEqual({ key: 'off_topic', label: 'off-topic' })
  })
  // glob, not node:fs: tsc keeps vite/client only; an absent file gives an empty glob and skips the test.
  const found = import.meta.glob('../../../../backend/app/core/triage.py', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
  const src = Object.values(found)[0]
  it.skipIf(!src)('equals the backend', () => {
    const block = src.slice(src.indexOf('REASONS'), src.indexOf('NOTE_MAX'))
    const backend: Record<string, string[]> = {}
    for (const m of block.matchAll(/"(\w+)": \(([^)]*)\)/g)) backend[m[1]] = [...m[2].matchAll(/"(\w+)"/g)].map((x) => x[1])
    const mine = Object.fromEntries(PILE_ORDER.map((p) => [p, REASONS[p].map((r) => r.key)]))
    expect(mine).toEqual(backend)
  })
})
