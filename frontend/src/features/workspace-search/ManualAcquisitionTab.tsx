import { useSearchHits, useUploadHitPdf } from '@/api/queries'

/** Hits stage-1 marked relevant but with no free PDF found automatically (Task 9/11's `import_hits` leaves these
 * `acquisition_status: 'failed'`). The user finds a copy themselves and uploads it here. */
export function ManualAcquisitionTab({ workspaceId }: { workspaceId: string }) {
  const { data } = useSearchHits(workspaceId, undefined, 'failed')
  const upload = useUploadHitPdf(workspaceId)
  const rows = data?.pages.flatMap((page) => page.items) ?? []

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 p-3">
      {rows.length === 0 && (
        <p className="text-sm text-muted-foreground">Nothing needs manual acquisition right now.</p>
      )}
      {rows.map((hit) => (
        <div key={hit.id} className="flex items-center justify-between gap-3 border-b pb-2 text-sm">
          <span className="flex-1 truncate">{hit.normalized_title}</span>
          <a
            href={`https://scholar.google.com/scholar?q=${encodeURIComponent(hit.normalized_title)}`}
            target="_blank"
            rel="noreferrer"
          >
            Search by title
          </a>
          <label>
            <span className="sr-only">{`Upload PDF for ${hit.normalized_title}`}</span>
            <input
              type="file"
              accept="application/pdf"
              aria-label={`Upload PDF for ${hit.normalized_title}`}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) upload.mutate({ hitId: hit.id, file })
              }}
            />
          </label>
        </div>
      ))}
      {upload.isError && (
        <p role="alert" className="text-xs text-destructive">
          {upload.error.message}
        </p>
      )}
    </div>
  )
}
