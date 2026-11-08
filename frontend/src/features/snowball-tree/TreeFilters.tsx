import type { ProvenanceOut } from '@/api/client'
import { primaryParent } from './layout'

export type Filters = { decision: string; level: string; direction: string; run: string }
export const NO_FILTERS: Filters = { decision: '', level: '', direction: '', run: '' }

const decisionKey = (d: string | null | undefined) => (d === 'relevant' || d === 'not_relevant' ? d : 'none')

/** Ids of nodes that do not match. The run filter matches on the run of the link that brought the node in. */
export function hiddenIds(data: ProvenanceOut, f: Filters): Set<string> {
  const via = primaryParent(data.links, data.roots, data.nodes)
  const out = new Set<string>()
  for (const n of data.nodes) {
    const link = via.get(n.id)
    const ok =
      (!f.decision || decisionKey(n.decision) === f.decision) &&
      (!f.level || String(n.level) === f.level) &&
      (!f.direction || link?.kind === f.direction) &&
      (!f.run || link?.run_id === f.run)
    if (!ok) out.add(n.id)
  }
  return out
}

const SELECT = 'h-8 rounded-md border border-input bg-background px-2 text-sm'

export function TreeFilters({ data, value, onChange }: { data: ProvenanceOut; value: Filters; onChange: (f: Filters) => void }) {
  const set = (key: keyof Filters) => (e: React.ChangeEvent<HTMLSelectElement>) => onChange({ ...value, [key]: e.target.value })
  const field = (label: string, key: keyof Filters, options: [string, string][]) => (
    <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
      {label}
      <select aria-label={label} className={SELECT} value={value[key]} onChange={set(key)}>
        <option value="">All</option>
        {options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}
      </select>
    </label>
  )
  return (
    <div className="flex flex-wrap gap-3">
      {field('Decision', 'decision', [['relevant', 'Included'], ['not_relevant', 'Excluded'], ['none', 'Not screened']])}
      {field('Level', 'level', data.levels.map((l) => [String(l.level), `Level ${l.level}`]))}
      {field('Direction', 'direction', [['cites', 'Its references'], ['cited_by', 'Papers citing it']])}
      {field('Run', 'run', data.roots.filter((r) => r.id.startsWith('root:') && r.id !== 'root:hand').map((r) => [r.id.slice(5), r.label]))}
    </div>
  )
}
