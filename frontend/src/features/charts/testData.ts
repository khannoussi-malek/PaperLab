import type { ResolvedCell, ResolvedData, ResolvedDataset, SeriesChartSpec, SeriesSpec } from '@/api/client'

/** A readable fake uuid: id(3) → 00000000-0000-4000-8000-000000000003. */
export const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`

export function cell(raw: string, value: number | null, extra: Partial<ResolvedCell> = {}): ResolvedCell {
  return { raw, value, error: null, origin: 'extracted', original_raw: null, page: null, bbox: null, ...extra }
}

export const BERT = id(1)
export const SYSTEM = id(11)
export const F1 = id(12)
export const STD = id(13)
export const BERT_B = id(101)
export const BERT_L = id(102)

/** BERT's Table 2 on page 6 of paper id(900): a label column, F1 with ± errors, and a spread column. */
export const bertTable: ResolvedDataset = {
  id: BERT,
  name: 'Table 2',
  kind: 'table',
  paper_id: id(900),
  paper_title: 'BERT',
  page: 6,
  region: [72, 100, 540, 160],
  columns: [
    { id: SYSTEM, name: 'System', unit: null },
    { id: F1, name: 'F1', unit: null },
    { id: STD, name: 'Std', unit: null },
  ],
  rows: [
    {
      id: BERT_B,
      position: 0,
      cells: {
        [SYSTEM]: cell('BERT-B', null, { page: 6, bbox: [[72, 120, 140, 130]] }),
        [F1]: cell('88.5 ± 0.3', 88.5, { error: 0.3, page: 6, bbox: [[220, 120, 280, 130]] }),
        [STD]: cell('0.4', 0.4, { page: 6, bbox: [[320, 120, 360, 130]] }),
      },
    },
    {
      id: BERT_L,
      position: 1,
      cells: {
        [SYSTEM]: cell('BERT-L', null, { page: 6, bbox: [[72, 134, 140, 144]] }),
        // Edited by the owner: extraction read 90.8.
        [F1]: cell('90.9', 90.9, { original_raw: '90.8', page: 7, bbox: [[220, 20, 280, 30]] }),
        [STD]: cell('0.2', 0.2, { page: 6, bbox: [[320, 134, 360, 144]] }),
      },
    },
  ],
}

export const MINE = id(2)
export const RUN = id(21)
export const SCORE = id(22)
export const RUN_1 = id(201)

export const ownData: ResolvedDataset = {
  id: MINE,
  name: 'runs.csv',
  kind: 'user',
  paper_id: null,
  paper_title: null,
  page: null,
  region: null,
  columns: [
    { id: RUN, name: 'Run', unit: null },
    { id: SCORE, name: 'Score', unit: '%' },
  ],
  rows: [{ id: RUN_1, position: 0, cells: { [RUN]: cell('mine', null, { origin: 'human' }), [SCORE]: cell('92', 92, { origin: 'human' }) } }],
}

export const GRID = id(3)
export const GX = id(31)
export const GY = id(32)
export const GZ = id(33)

/** Long format: one row per (x, y), with one gap at (2, 20). */
export const longGrid: ResolvedDataset = {
  id: GRID,
  name: 'sweep',
  kind: 'user',
  paper_id: null,
  paper_title: null,
  page: null,
  region: null,
  columns: [
    { id: GX, name: 'lr', unit: null },
    { id: GY, name: 'layers', unit: null },
    { id: GZ, name: 'loss', unit: null },
  ],
  rows: [
    [1, 10, 0.9],
    [2, 10, 0.7],
    [1, 20, 0.5],
  ].map(([x, y, z], i) => ({
    id: id(300 + i),
    position: i,
    cells: {
      [GX]: cell(String(x), x, { origin: 'human' }),
      [GY]: cell(String(y), y, { origin: 'human' }),
      [GZ]: cell(String(z), z, { origin: 'human' }),
    },
  })),
}

export const data = (...datasets: ResolvedDataset[]): ResolvedData => ({ datasets, missing: [] })

export function series(overrides: Partial<SeriesSpec> = {}): SeriesSpec {
  return { id: 's1', name: '', dataset_id: BERT, x: SYSTEM, y: F1, error: 'none', trend: 'none', multiply: 1, ...overrides }
}

export function seriesChart(type: SeriesChartSpec['type'], list: SeriesSpec[], extra: Partial<SeriesChartSpec> = {}): SeriesChartSpec {
  return { version: 1, type, series: list, ...extra }
}
