import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, type Role, type SectionReview } from '@/api/client'
import { remoteHost } from './reviewModel'

const POLL_MS = 2000
const NONE: SectionReview[] = []

const START_ERRORS: Record<string, string> = {
  unknown_role: 'Pick what kind of section this is.',
  no_section: 'Put the cursor inside a section first.',
  section_too_long: 'That section is too long to review at once. Review it in parts.',
  no_model: 'Add a model in Settings to run the reviewer.',
  review_running: 'A review is already running.',
  file_changed: 'The file changed. Try again.',
}

/** A refused start in plain words; null for the remote-model question, which is asked, not shown. */
export function sectionStartError(e: unknown): string | null {
  if (remoteHost(e)) return null
  if (e instanceof ApiError && START_ERRORS[e.code]) return START_ERRORS[e.code]
  return e instanceof Error ? e.message : 'Something went wrong. Please try again.'
}

export type SectionStart = { base: string; at: number; role: Role | null; confirmRemote: boolean }

/** The open file's section reviews; polls while one is queued or running. */
export function useSectionReview(manuscriptId: string, file: string, enabled = true) {
  const qc = useQueryClient()
  const key = ['manuscriptSectionReview', manuscriptId, file]
  const state = useQuery({
    queryKey: key,
    queryFn: () => api.sectionReviews(manuscriptId, file),
    enabled,
    refetchInterval: (q) => (q.state.data?.reviews.some((r) => r.status === 'queued' || r.status === 'running') ? POLL_MS : false),
  })
  const refresh = () => qc.invalidateQueries({ queryKey: key })
  const start = useMutation({
    mutationFn: ({ base, at, role, confirmRemote }: SectionStart) =>
      api.startSectionReview(manuscriptId, { file, base, at, role, confirm_remote: confirmRemote }),
    onSettled: refresh,
  })
  const cancel = useMutation({ mutationFn: (id: string) => api.cancelSectionReview(manuscriptId, id), onSettled: refresh })
  const reviews = state.data?.reviews ?? NONE
  return {
    reviews,
    live: reviews.some((r) => r.status === 'queued' || r.status === 'running'),
    /** `base` is the file's updated_at, `at` the cursor (UTF-16); `role` only when the researcher overrode the guess. */
    start: (s: SectionStart) => start.mutateAsync(s),
    cancel: (id: string) => cancel.mutateAsync(id),
  }
}
