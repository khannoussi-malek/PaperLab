import { useEmbeddingStatus } from '@/api/queries'
import { DownloadSearchModel } from '@/features/settings/DownloadSearchModel'
import { showSearchNotice } from '@/features/settings/searchModel'
import { rebuildLine } from '@/features/settings/searchSources'
import { settingsSectionHref } from '@/lib/route'

/**
 * One quiet line under the library header, only when there is something to say:
 * - while search is being rebuilt with a new source, how far it got (P1, D156);
 * - otherwise, while Built-in is the source without its model and some paper is too long to chat with whole (M23's
 *   P1), that search isn't set up, with the Download button and a way to another source.
 */
export function SearchNotice() {
  const status = useEmbeddingStatus()
  if (status.data === undefined) return null
  const { rebuild, source } = status.data
  if (rebuild) {
    return <p className="search-notice text-sm tabular-nums text-muted-foreground">{rebuildLine(source.label, rebuild)}</p>
  }
  if (!showSearchNotice(status.data)) return null
  return (
    <div className="search-notice flex flex-wrap items-start gap-x-3 gap-y-2 text-sm text-muted-foreground">
      <p className="py-1.5">Search isn't set up: long papers and workspaces can't be searched yet.</p>
      <DownloadSearchModel />
      <a href={settingsSectionHref('search')} className="py-1.5 underline-offset-4 hover:text-foreground hover:underline">
        Use another search source
      </a>
    </div>
  )
}
