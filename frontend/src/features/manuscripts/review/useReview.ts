import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, type ReviewState } from '@/api/client'
import { remoteHost } from './reviewModel'

const POLL_MS = 2000

const START_ERRORS: Record<string, string> = {
  too_many_claims: "That's more than 30 citations to check at once. Select a smaller part and try again.",
  no_model: 'Add a model in Settings to run the reviewer.',
  review_running: 'A check is already running.',
  file_changed: 'The file changed. Try again.',
}

export function reviewStartError(e: unknown): string {
  if (e instanceof ApiError) {
    const hit = Object.keys(START_ERRORS).find((k) => e.code.startsWith(k))
    if (hit) return START_ERRORS[hit]
  }
  return e instanceof Error ? e.message : 'Something went wrong. Please try again.'
}

export type ReviewSelection = { from?: number | null; to?: number | null; includeUncited?: boolean }

export function useReview(manuscriptId: string, file: string, enabled = true) {
  const qc = useQueryClient()
  const key = ['manuscriptReview', manuscriptId, file]
  const state = useQuery({
    queryKey: key,
    queryFn: () => api.reviewState(manuscriptId, file),
    enabled,
    refetchInterval: (q) => {
      const s = (q.state.data as ReviewState | undefined)?.run?.status
      return s === 'queued' || s === 'running' ? POLL_MS : false
    },
  })
  const refresh = () => qc.invalidateQueries({ queryKey: key })
  const start = useMutation({
    mutationFn: ({ base, selection, confirmRemote }: { base: string; selection?: ReviewSelection; confirmRemote: boolean }) =>
      api.startReview(manuscriptId, { file, base, from: selection?.from, to: selection?.to, include_uncited: selection?.includeUncited, confirm_remote: confirmRemote }),
    onSettled: refresh,
  })
  const cancel = useMutation({
    mutationFn: () => {
      const id = state.data?.run?.id
      return id ? api.cancelReview(manuscriptId, id) : Promise.resolve(null)
    },
    onSettled: refresh,
  })
  const dismiss = useMutation({ mutationFn: (hash: string) => api.dismissClaim(manuscriptId, hash), onSettled: refresh })
  const restore = useMutation({ mutationFn: (hash: string) => api.restoreClaim(manuscriptId, hash), onSettled: refresh })
  return {
    state: state.data,
    /** The run for the open file; the latest run may belong to another file. */
    run: state.data?.run?.file === file ? state.data.run : null,
    /** The manuscript's latest run whatever its file: drives the menu's progress line and Cancel. */
    anyRun: state.data?.run ?? null,
    items: state.data?.items ?? [],
    dismissed: state.data?.dismissed ?? [],
    isLoading: state.isLoading,
    /** `base` is the file's updated_at; the selection (UTF-16 offsets) limits the check to part of the file. */
    start: (base: string, selection?: ReviewSelection, confirmRemote = false) => start.mutateAsync({ base, selection, confirmRemote }),
    cancel: () => cancel.mutateAsync(),
    dismiss: (hash: string) => dismiss.mutateAsync(hash),
    restore: (hash: string) => restore.mutateAsync(hash),
    startError: start.error && !remoteHost(start.error) ? reviewStartError(start.error) : null,
    /** Set when the start needs a yes before the text goes to a remote model; Send starts again with confirmRemote. */
    confirmHost: remoteHost(start.error),
    dismissConfirm: () => start.reset(),
  }
}

export type CiteProposal = {
  paperId: string
  key: string
  quote: string
  page: number | null
  chunkId: string | null
  /** The model's verdict, or 'passage' when only a passage of the paper matched. */
  verdict: 'supported' | 'partially_supported' | 'passage'
}

export const NO_PROPOSALS = 'No paper in this workspace speaks to this.'
const MAX_PROPOSALS = 3

/** On demand: `ask()` finds evidence for the sentence; proposals fill in as verdicts arrive. */
export function useCiteProposals(manuscriptId: string, sentencePlain: string) {
  type Found = Awaited<ReturnType<typeof api.findEvidence>>
  const [asked, setAsked] = useState<{ sentence: string; found: Found } | null>(null)
  const found = asked?.sentence === sentencePlain ? asked.found : null // an edited sentence drops the old answer
  const [failed, setFailed] = useState<string | null>(null)
  const [finding, setFinding] = useState(false)
  const [confirmHost, setConfirmHost] = useState<string | null>(null)
  const ticket = useRef(0)
  useEffect(() => () => { ticket.current += 1 }, [])

  const ask = (confirmRemote = false) => {
    const mine = ++ticket.current
    const before = { asked, failed } // a remote refusal puts these back: Cancel leaves the row as it was
    setAsked(null); setFailed(null); setFinding(true); setConfirmHost(null)
    api.findEvidence(manuscriptId, sentencePlain, confirmRemote).then(
      (f) => { if (ticket.current === mine) { setAsked({ sentence: sentencePlain, found: f }); setFinding(false) } },
      (e) => {
        if (ticket.current !== mine) return
        const host = remoteHost(e)
        if (host) { setAsked(before.asked); setFailed(before.failed); setConfirmHost(host) }
        else setFailed(e instanceof Error ? e.message : 'Something went wrong. Please try again.')
        setFinding(false)
      },
    )
  }

  const hash = found?.sentence_hash
  const unavailable = found?.verdicts === 'unavailable'
  const rows = useQuery({
    queryKey: ['manuscriptEvidence', manuscriptId, hash],
    queryFn: () => api.evidenceRows(manuscriptId, hash!),
    enabled: !!hash && !unavailable,
    gcTime: 0,
    refetchInterval: (q) => {
      if (q.state.status === 'error') return false
      const d = q.state.data
      return !d || d.some((r) => r.status === 'queued' || r.status === 'running') ? POLL_MS : false
    },
  })

  const byPaper = new Map((rows.data ?? []).map((r) => [r.paper_id, r]))
  const withVerdict: CiteProposal[] = []
  const passageOnly: CiteProposal[] = []
  for (const p of found?.papers ?? []) {
    const row = byPaper.get(p.paper_id)
    const good = row?.status === 'done' && (row.verdict === 'supported' || row.verdict === 'partially_supported')
    if (good && row.quote) {
      const passage = p.passages.find((x) => x.page === row.page) ?? p.passages[0]
      withVerdict.push({ paperId: p.paper_id, key: p.key, quote: row.quote, page: row.page, chunkId: passage?.chunk_id ?? null, verdict: row.verdict as CiteProposal['verdict'] })
    } else if (p.passages[0]) {
      const top = p.passages[0]
      passageOnly.push({ paperId: p.paper_id, key: p.key, quote: top.text, page: top.page, chunkId: top.chunk_id, verdict: 'passage' })
    }
  }
  const proposals = [...withVerdict, ...passageOnly].slice(0, MAX_PROPOSALS)
  const settled = !!found && !finding && (unavailable || rows.isError || (!!rows.data && !rows.data.some((r) => r.status === 'queued' || r.status === 'running')))
  const pending = finding || (!!found && !settled)
  return {
    ask: () => ask(),
    /** Set when the find needs a yes before the sentence goes to a remote model; confirm asks again with it. */
    confirmHost,
    confirm: () => ask(true),
    dismissConfirm: () => setConfirmHost(null),
    proposals,
    pending,
    message: failed ?? (found && !pending && proposals.length === 0 ? NO_PROPOSALS : null),
  }
}
