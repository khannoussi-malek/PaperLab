import { useState } from 'react'
import type { Hit } from '@/entities'
import type { useAcceptSuggestions, useBulkPatchSearchHits } from '@/services/queries'
import { EXCLUDE_REASONS } from '@/features/search/hitReview'

export type ExcludeReason = (typeof EXCLUDE_REASONS)[number]

/** Multi-select stage-1 triage over the visible rows: checked ids plus the bulk actions that apply to them. */
export function useHitSelection(
  visibleRows: Hit[],
  bulkPatch: ReturnType<typeof useBulkPatchSearchHits>,
  acceptSuggestions: ReturnType<typeof useAcceptSuggestions>,
) {
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set())
  const [bulkReason, setBulkReason] = useState<ExcludeReason | ''>('')

  // Multi-select stage-1 triage: the same decision HitMenu/HitPreview apply one hit at a time, applied to every
  // checked row in a single request (useBulkPatchSearchHits). Selection is cleared optimistically on click, same
  // as ScreeningTab's confirmExclude — a failed request shows via bulkPatch.isError and the rows stay re-selectable.
  const allVisibleChecked = visibleRows.length > 0 && visibleRows.every((hit) => checkedIds.has(hit.id))
  const someVisibleChecked = visibleRows.some((hit) => checkedIds.has(hit.id))

  function toggleChecked(hitId: string) {
    setCheckedIds((prev) => {
      const next = new Set(prev)
      if (next.has(hitId)) next.delete(hitId)
      else next.add(hitId)
      return next
    })
  }

  function toggleCheckAllVisible() {
    setCheckedIds(allVisibleChecked ? new Set() : new Set(visibleRows.map((hit) => hit.id)))
  }

  function bulkMark(stage1_status: 'relevant' | 'maybe') {
    bulkPatch.mutate({ hit_ids: [...checkedIds], stage1_status })
    setCheckedIds(new Set())
  }

  function bulkAccept() {
    acceptSuggestions.mutate([...checkedIds])
    setCheckedIds(new Set())
  }

  function bulkMarkNotRelevant() {
    if (!bulkReason) return
    bulkPatch.mutate({ hit_ids: [...checkedIds], stage1_status: 'not_relevant', stage1_exclude_reason: bulkReason })
    setCheckedIds(new Set())
    setBulkReason('')
  }

  return {
    checkedIds,
    bulkReason,
    setBulkReason,
    allVisibleChecked,
    someVisibleChecked,
    toggleChecked,
    toggleCheckAllVisible,
    bulkMark,
    bulkAccept,
    bulkMarkNotRelevant,
    clearChecked: () => setCheckedIds(new Set()),
  }
}
