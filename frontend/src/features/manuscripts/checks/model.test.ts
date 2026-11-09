import { expect, test } from 'vitest'
import type { CheckFinding, CheckRunResult } from '@/api/client'
import { badgeOf, groupByCheck, rowsOf, summary } from './model'

const f = (check: string, severity: CheckFinding['severity'], line = 1): CheckFinding =>
  ({ check, severity, file: 'main.tex', line, message: 'm', fix_hint: null })
const run = (findings: CheckFinding[], ran = ['a.one', 'b.two']): CheckRunResult => ({
  ran, findings,
  counts: { error: findings.filter((x) => x.severity === 'error').length, warning: findings.filter((x) => x.severity === 'warning').length, info: findings.filter((x) => x.severity === 'info').length },
})

test('badge counts errors and warnings only, with its tone', () => {
  expect(badgeOf(undefined)).toBeNull()
  expect(badgeOf(run([f('a.one', 'info')]))).toEqual({ count: 0, tone: 'clean' })
  expect(badgeOf(run([f('a.one', 'warning'), f('a.one', 'warning')]))).toEqual({ count: 2, tone: 'warning' })
  expect(badgeOf(run([f('a.one', 'warning'), f('a.one', 'error')]))).toEqual({ count: 2, tone: 'error' })
})

test('groups follow the order of ran, skip checks with no findings, and keep server order inside', () => {
  const groups = groupByCheck(run([f('b.two', 'error', 5), f('a.one', 'info', 2), f('b.two', 'warning', 1)]))
  expect(groups.map((g) => g.check)).toEqual(['a.one', 'b.two'])
  expect(groups[1].findings.map((x) => x.line)).toEqual([5, 1])
  expect(groups[1].counts).toEqual({ error: 1, warning: 1, info: 0 })
})

test('summary text pluralises and omits zeros', () => {
  expect(summary({ error: 2, warning: 1, info: 0 })).toBe('2 errors, 1 warning')
  expect(summary({ error: 1, warning: 0, info: 3 })).toBe('1 error, 3 infos')
})

test('rowsOf caps at 20 and says how many more', () => {
  const many = Array.from({ length: 23 }, (_, i) => f('a.one', 'warning', i))
  expect(rowsOf(many)).toEqual({ rows: many.slice(0, 20), more: 3 })
  expect(rowsOf(many.slice(0, 2))).toEqual({ rows: many.slice(0, 2), more: 0 })
})
