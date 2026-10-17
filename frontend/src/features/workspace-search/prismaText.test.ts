import { expect, test } from 'vitest'
import type { PrismaExportOut } from '@/api/client'
import { prismaCsv, prismaText } from './prismaText'

const data: PrismaExportOut = {
  identified: 120, duplicates_removed: 20, stage1_screened: 100, stage1_excluded: 42,
  stage1_excluded_by_reason: { wrong_topic: 40, unspecified: 2 },
  sought: 58, not_retrieved: 6, stage2_assessed: 52, stage2_excluded: 14,
  stage2_excluded_by_reason: { 'wrong population': 14 },
  included: 38, runs: [], automation: [], notes: [], screening_criteria: null,
}

// Tiny RFC 4180 parser: quoted fields, doubled quotes, newlines inside quotes.
function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++ }
      else if (c === '"') quoted = false
      else cell += c
    } else if (c === '"') quoted = true
    else if (c === ',') { row.push(cell); cell = '' }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = '' }
    else cell += c
  }
  if (cell || row.length) { row.push(cell); rows.push(row) }
  return rows
}

test('prismaText lists every box with its reasons', () => {
  const text = prismaText(data, 'All runs (combined)')
  expect(text).toContain('All runs (combined)')
  for (const l of ['Identified: 120', 'Duplicates removed: 20', 'Screened on title & abstract: 100', 'Reports sought: 58', 'Not retrieved: 6', 'Full texts assessed: 52', 'Included: 38'])
    expect(text).toContain(l)
  expect(text).toContain('Excluded on title & abstract: 42 (Wrong topic: 40, No reason given: 2)')
  expect(text).toContain('Excluded after full text: 14 (wrong population: 14)')
})

test('prismaCsv escapes a query with a comma, a quote and a newline', () => {
  const rows = parseCsv(prismaCsv(data, 'a, "b"\nc'))
  expect(rows[0]).toEqual(['stage', 'box', 'count', 'reasons'])
  expect(rows.length).toBe(11)
  for (const r of rows) expect(r).toHaveLength(4)
  expect(rows.some((r) => r.includes('a, "b"\nc'))).toBe(true)
})

test('prismaCsv defuses spreadsheet formulas in text but not counts', () => {
  const csv = prismaCsv(data, '=HYPERLINK("x")')
  expect(csv).toContain(`"'=HYPERLINK(""x"")"`)
  expect(csv).toContain('"Identified","120"')
  expect(csv).not.toContain("'120")
  expect(prismaCsv(data, '-covid')).toContain(`"'-covid"`)
})
