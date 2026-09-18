import { describe, expect, it } from 'vitest'
import { entryAt, joinLines, labelOf, pageColumns, type PageText, type TextBox } from './citationEntry'

const LEFT = 54
const RIGHT = 316

/** A 9 pt text item at 4.5 pt a character, never wider than a column, with its baseline at `base`. */
const box = (str: string, x0: number, base: number, h = 9): TextBox => ({
  str,
  x0,
  x1: x0 + Math.min(4.5 * str.length, 220),
  base,
  h,
})

/**
 * `[N]` at `x`, PDF.js's own space item after it, then the lines 11 pt apart at `x + 16`, the first on the label's
 * baseline: a reference list as PDF.js reads the fixture.
 */
const entry = (label: number, x: number, base: number, lines: string[]): TextBox[] => [
  box(`[${label}]`, x, base),
  { str: ' ', x0: x + 13.5, x1: x + 16, base, h: 0 },
  ...lines.map((line, k) => box(line, x + 16, base + 11 * k)),
]

/** A US Letter page. */
const page = (boxes: TextBox[], number = 2): PageText => ({ page: number, width: 612, columns: pageColumns(boxes, 612) })

const texts = (columns: { text: string }[][]) => columns.map((column) => column.map((line) => line.text))

describe('columns and lines', () => {
  it('reads two columns when at most two boxes cross the middle, and one column otherwise', () => {
    const lists = [box('Left column text', LEFT, 100), box('Right column text', RIGHT, 100)]
    const title = box('A title spanning both columns of the page here', 150, 60)
    expect(texts(pageColumns([...lists, title, { ...title, base: 70 }], 612))).toEqual([
      ['A title spanning both columns of the page here', 'A title spanning both columns of the page here', 'Left column text'],
      ['Right column text'],
    ])
    const prose = [60, 70, 80].map((base) => box('Body text that runs across the whole page width', 150, base))
    expect(pageColumns([...lists, ...prose], 612)).toHaveLength(1)
  })

  it('joins boxes on one baseline into a line, and ends it at a gap over 12 pt', () => {
    const boxes = [box('[1]', LEFT, 100), box(' ', 67.5, 100.4, 0), box('Ada Fixture.', 70, 100.4), box('sidebar', 140, 100)]
    const [left] = pageColumns(boxes, 612)
    expect(left.map((line) => line.text)).toEqual(['[1] Ada Fixture.'])
    expect(left[0].x1).toBe(124)
  })

  it('takes only [N] as a label', () => {
    expect(labelOf({ text: '[51] Ada Fixture.' })).toBe(51)
    expect(labelOf({ text: '12. Ada Fixture. 2019.' })).toBeNull()
    expect(labelOf({ text: '2019. [51] in a sentence' })).toBeNull()
  })
})

describe('the label under a destination', () => {
  const list = page(entry(7, LEFT, 200, ['Ada Fixture. 2026. A title.']))

  it('is found from one label-height above the destination to 2.5 below', () => {
    expect(entryAt(list, null, { x: LEFT, y: 209 })?.label).toBe(7) // the baseline 1 h above
    expect(entryAt(list, null, { x: LEFT, y: 177.5 })?.label).toBe(7) // 2.5 h below
  })

  it('is not found outside that window, so the link is not a citation', () => {
    expect(entryAt(list, null, { x: LEFT, y: 209.5 })).toBeNull()
    expect(entryAt(list, null, { x: LEFT, y: 177 })).toBeNull()
  })

  it('is looked for in the destination\'s column, or in both (nearest) when the link gives no x', () => {
    const two = page([...entry(3, LEFT, 200, ['Left entry.']), ...entry(9, RIGHT, 205, ['Right entry.'])])
    expect(entryAt(two, null, { x: RIGHT, y: 190 })?.label).toBe(9)
    expect(entryAt(two, null, { x: null, y: 190 })?.label).toBe(3)
    expect(entryAt(two, null, { x: null, y: 204 })?.label).toBe(9)
  })
})

describe('the entry\'s body', () => {
  it('stops at the next label at the same indent, but not at a [12] at another indent', () => {
    const list = page([
      ...entry(4, LEFT, 200, ['Ada Fixture. As shown in', '[12] and more. A title.']),
      ...entry(5, LEFT, 222, ['Next entry.']),
    ])
    expect(entryAt(list, null, { x: LEFT, y: 190 })?.entry?.text).toBe('[4] Ada Fixture. As shown in [12] and more. A title.')
  })

  it('stops at a gap over 2.6 label-heights', () => {
    const list = page([...entry(4, LEFT, 200, ['Ada Fixture.', 'A title.']), box('Unrelated text.', LEFT, 235)])
    expect(entryAt(list, null, { x: LEFT, y: 190 })?.entry?.lines).toEqual(['[4] Ada Fixture.', 'A title.'])
  })

  it('joins a line ending in a hyphen straight onto the next, keeping the hyphen', () => {
    expect(joinLines(['doi:10.5555/paperlab-e2e-', 'free', 'more'])).toBe('doi:10.5555/paperlab-e2e-free more')
    const list = page(entry(1, LEFT, 200, ['Journal. doi:10.5555/paperlab-e2e-', 'free']))
    expect(entryAt(list, null, { x: LEFT, y: 190 })?.entry?.text).toBe('[1] Journal. doi:10.5555/paperlab-e2e-free')
  })
})

describe('an entry that runs on', () => {
  const header = box('Fixture Proceedings 2026', 430, 40, 8)

  it('continues above [N+1] at the top of the right column, without the running header', () => {
    const list = page([
      ...entry(2, LEFT, 729, ['Ada Fixture, and', 'Dee Sample. 2026.']),
      box('2', LEFT, 772, 8),
      header,
      box('The Title. Journal of', RIGHT + 16, 70),
      box('Fixtures.', RIGHT + 16, 81),
      ...entry(3, RIGHT, 96, ['Some Author.']),
    ])
    const found = entryAt(list, null, { x: LEFT, y: 718 })?.entry
    expect(found?.text).toBe('[2] Ada Fixture, and Dee Sample. 2026. The Title. Journal of Fixtures.')
    expect(found?.rects).toHaveLength(4) // the right column is on the same page
  })

  it('continues on the next page from the right column, and flashes only the lines on the label\'s page', () => {
    const here = page(entry(6, RIGHT, 740, ['Ada Fixture.']), 2)
    const next = page([box('The Title.', LEFT + 16, 60), ...entry(7, LEFT, 71, ['Another.'])], 3)
    const found = entryAt(here, next, { x: RIGHT, y: 730 })?.entry
    expect(found?.text).toBe('[6] Ada Fixture. The Title.')
    expect(found?.page).toBe(2)
    expect(found?.rects).toEqual([[RIGHT, 731, RIGHT + 70, 742.25]])
  })

  it('does not continue without an [N+1] to continue above', () => {
    const list = page([...entry(8, LEFT, 740, ['The last entry.']), box('Stray text.', RIGHT + 16, 70)])
    expect(entryAt(list, null, { x: LEFT, y: 730 })?.entry?.text).toBe('[8] The last entry.')
  })
})

describe('the caps', () => {
  const lines = (count: number, text = 'A line.') => Array.from({ length: count }, () => text)
  const at = { x: LEFT, y: 90 }

  it('reads 12 lines and 1,200 characters', () => {
    expect(entryAt(page(entry(1, LEFT, 100, lines(12))), null, at)?.entry?.lines).toHaveLength(12)
    const long = entryAt(page(entry(1, LEFT, 100, lines(7, 'x'.repeat(170)))), null, at)
    expect(long?.entry?.text).toHaveLength(1200)
  })

  it('gives no entry past 12 lines or 1,200 characters, but still the label and a strip to jump to', () => {
    const tall = entryAt(page(entry(1, LEFT, 100, lines(13))), null, at)
    expect(tall?.label).toBe(1)
    expect(tall?.entry).toBeNull()
    expect(tall?.jump).toEqual({ page: 2, rects: [[LEFT, 90, LEFT + 16 + 31.5, 102]] })
    const wide = entryAt(page(entry(1, LEFT, 100, [...lines(6, 'x'.repeat(170)), 'x'.repeat(171)])), null, at)
    expect(wide?.entry).toBeNull()
  })
})
