import { PersistentRail } from '@/layout/PersistentRail'
import { useKeptCount } from './features/manuscripts/keptTexts'
import { useLeaveWarning } from './features/manuscripts/useLeaveWarning'
import { downloadAnnouncement } from './features/settings/searchModel'
import { useSearchModelDownload } from './features/settings/useSearchModelDownload'
import { RouterView } from './router/RouterView'

export default function App() {
  const { state } = useSearchModelDownload()
  useLeaveWarning(useKeptCount() > 0) // a manuscript's unsaved text outlives its page, so the warning does too
  return (
    <>
      {/* Lives at the root, not in SearchNotice or the chat block: both unmount as soon as the status refetch
          reports the model present, which would drop this announcement if it lived inside them. Polite, and empty
          except right when the download finishes, so it never reads the running progress. */}
      <p role="status" className="sr-only">
        {downloadAnnouncement(state)}
      </p>
      <RouterView />
      {/* After the page, so a new page's sidebar slot is in place before the sidebar measures (PersistentRail). */}
      <PersistentRail />
    </>
  )
}
