import type { CheckFinding, CheckRunResult } from '@/api/client'

export type Severity = CheckFinding['severity']
const CAP = 20

export const badgeOf = (r: CheckRunResult | undefined) =>
  !r ? null : { count: r.counts.error + r.counts.warning, tone: r.counts.error ? 'error' : r.counts.warning ? 'warning' : 'clean' } as const

export type Group = { check: string; findings: CheckFinding[]; counts: Record<Severity, number> }

export function groupByCheck(r: CheckRunResult): Group[] {
  return r.ran.flatMap((check) => {
    const findings = r.findings.filter((x) => x.check === check)
    const counts = { error: 0, warning: 0, info: 0 }
    findings.forEach((x) => { counts[x.severity] += 1 })
    return findings.length ? [{ check, findings, counts }] : []
  })
}

export const summary = (c: Record<Severity, number>) =>
  (['error', 'warning', 'info'] as const).filter((s) => c[s]).map((s) => `${c[s]} ${s}${c[s] === 1 ? '' : 's'}`).join(', ')

export const rowsOf = (findings: CheckFinding[]) => ({ rows: findings.slice(0, CAP), more: Math.max(0, findings.length - CAP) })
