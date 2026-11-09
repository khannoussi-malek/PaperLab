import type { ProvenanceOut } from '@/api/client'

const n = (id: string, level: number) => ({ id, title: `Paper ${id}`, level, snowballed: [], paths: 1 })
const l = (parent: string, child: string, kind: string, at = '2026-01-01T00:00:00Z') => ({ parent, child, kind, run_id: 'r1', created_at: at })

/** root:r1 -> A -cites-> B -cited_by-> C -cites-> D -cites-> E -cites-> F; G is a second child of A. */
export const prov = {
  roots: [{ id: 'root:r1', label: 'graph search', hit_count: 1, on_tree: 1, excluded_hidden: 0 }],
  nodes: [n('A', 0), n('B', 1), n('C', 2), n('D', 3), n('E', 4), n('F', 5), n('G', 1)],
  links: [
    l('root:r1', 'A', 'search'), l('A', 'B', 'cites'), l('B', 'C', 'cited_by'), l('C', 'D', 'cites'),
    l('D', 'E', 'cites'), l('E', 'F', 'cites'), l('A', 'G', 'cited_by'),
  ],
} as unknown as ProvenanceOut
