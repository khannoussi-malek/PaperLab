import { codeInWords } from '@/lib/errorWords'
import { errorText } from '@/features/search/schedule'
import { snowballMessage } from '@/features/search/ScreeningTab'
import type { useAcceptSuggestions, useBulkPatchSearchHits, useClearSearchHits, useImportAllHits, useImportSearchHits, usePatchSearchHit, useSnowball, useUploadHitPdf } from '@/services/queries'

/** The mutations whose outcome the hit table's single status line reports. */
export type HitTableMutations = {
  acceptSuggestions: ReturnType<typeof useAcceptSuggestions>
  bulkPatch: ReturnType<typeof useBulkPatchSearchHits>
  importHits: ReturnType<typeof useImportSearchHits>
  importAllHits: ReturnType<typeof useImportAllHits>
  clearHits: ReturnType<typeof useClearSearchHits>
  reviewHit: ReturnType<typeof usePatchSearchHit>
  uploadHitPdf: ReturnType<typeof useUploadHitPdf>
  snowball: ReturnType<typeof useSnowball>
}

// Collapses every mutation's own isError/isSuccess into the single line actually shown (see the render site
// in HitTable for why) — errors first, bulk/global actions before single-row ones, success notices last.
export function hitStatusMessage({
  acceptSuggestions,
  bulkPatch,
  importHits,
  importAllHits,
  clearHits,
  reviewHit,
  uploadHitPdf,
  snowball,
}: HitTableMutations): { tone: 'error' | 'status'; text: string } | null {
  return (
    (acceptSuggestions.isError && {
      tone: 'error' as const,
      text: errorText(acceptSuggestions.error.message) ?? acceptSuggestions.error.message,
    }) ||
    (bulkPatch.isError && { tone: 'error' as const, text: codeInWords(bulkPatch.error.message) }) ||
    (importHits.isError && { tone: 'error' as const, text: codeInWords(importHits.error.message) }) ||
    (importAllHits.isError && { tone: 'error' as const, text: codeInWords(importAllHits.error.message) }) ||
    (clearHits.isError && { tone: 'error' as const, text: codeInWords(clearHits.error.message) }) ||
    (reviewHit.isError && { tone: 'error' as const, text: codeInWords(reviewHit.error.message) }) ||
    (uploadHitPdf.isError && { tone: 'error' as const, text: codeInWords(uploadHitPdf.error.message) }) ||
    (snowball.isError && { tone: 'error' as const, text: codeInWords(snowball.error.message) }) ||
    // A "failed" import is a resolved response (see useImportSearchHits), not a rejected mutation — no free
    // copy was found automatically, which isn't an error so much as a cue to use the manual options already
    // in the preview panel.
    (importHits.isSuccess &&
      importHits.data.failed > 0 && {
        tone: 'status' as const,
        text: 'No PDF found automatically for that paper — try the options below, or upload one.',
      }) ||
    (snowball.isSuccess && { tone: 'status' as const, text: snowballMessage(snowball.data) }) ||
    (acceptSuggestions.isSuccess && {
      tone: 'status' as const,
      text: `Accepted ${acceptSuggestions.data.accepted}, skipped ${acceptSuggestions.data.skipped.length}`,
    }) ||
    null
  )
}
