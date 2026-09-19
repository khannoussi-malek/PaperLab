import { useEmbeddingStatus } from '@/api/queries'
import { DownloadSearchModel } from '@/features/settings/DownloadSearchModel'
import { showSearchNotice } from '@/features/settings/searchModel'

/**
 * P1: one quiet line under the library header while no search model is downloaded and some paper is too long to
 * chat with whole, with the Download button. It goes away once the model is here.
 */
export function SearchNotice() {
  const status = useEmbeddingStatus()
  if (status.data === undefined || !showSearchNotice(status.data)) return null
  return (
    <div className="search-notice flex flex-wrap items-start gap-x-3 gap-y-2 text-sm text-muted-foreground">
      <p className="py-1.5">Search isn't set up: long papers and workspaces can't be searched yet.</p>
      <DownloadSearchModel />
    </div>
  )
}
