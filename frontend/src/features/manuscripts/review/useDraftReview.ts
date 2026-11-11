import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { isLive, type DraftStart } from './draftReviewModel'

const POLL_MS = 2000

/** The manuscript's whole-draft review and its estimates; polls while one is queued or running. */
export function useDraftReview(manuscriptId: string) {
  const qc = useQueryClient()
  const key = ['manuscriptDraftReview', manuscriptId]
  const state = useQuery({
    queryKey: key,
    queryFn: () => api.draftReview(manuscriptId).then((s) => s.review),
    // A failing poll stops (as useSectionReview does) instead of spinning.
    refetchInterval: (q) => (q.state.status !== 'error' && isLive(q.state.data) ? POLL_MS : false),
  })
  const estimate = useQuery({
    queryKey: ['manuscriptDraftReviewEstimate', manuscriptId],
    queryFn: () => api.draftReviewEstimate(manuscriptId),
  })
  const refresh = () => qc.invalidateQueries({ queryKey: key })
  const start = useMutation({ mutationFn: (body: DraftStart) => api.startDraftReview(manuscriptId, body), onSettled: refresh })
  const cancel = useMutation({ mutationFn: (reviewId: string) => api.cancelDraftReview(manuscriptId, reviewId), onSettled: refresh })
  return {
    review: state.data ?? null,
    estimate: estimate.data ?? null,
    estimateFailed: estimate.isError,
    start: (body: DraftStart) => start.mutateAsync(body),
    cancel: (reviewId: string) => cancel.mutateAsync(reviewId),
  }
}
