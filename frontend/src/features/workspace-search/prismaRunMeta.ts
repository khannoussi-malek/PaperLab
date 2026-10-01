import type { PrismaExportOut } from '@/api/client'

/** `PrismaExportOut.runs` comes back as `Record<string, unknown>[]` — the backend returns `list[dict]` (see
 * `prisma_export` in `backend/app/core/prisma_export.py`), so openapi-typescript can't infer a precise shape.
 * This is the slice of each run dict's real keys `PrismaTab`'s per-run <select>/detail panel and
 * `ReadingQueueTab`'s own run picker actually need — shared here so neither duplicates the mapping. */
export type PrismaRunMeta = { id: string; query_text: string; filters_json: Record<string, unknown>; started_at: string }

export function asPrismaRunMeta(runs: PrismaExportOut['runs']): PrismaRunMeta[] {
  return runs.map((r) => ({
    id: String(r.id),
    query_text: String(r.query_text),
    filters_json: (r.filters_json as Record<string, unknown> | undefined) ?? {},
    started_at: String(r.started_at),
  }))
}
