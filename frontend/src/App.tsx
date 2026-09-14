import { LibraryPage } from './features/library/LibraryPage'
import { ReaderPage } from './features/reader/ReaderPage'
import { useRoute } from './lib/route'

export default function App() {
  const route = useRoute()
  if (route.name === 'reader') {
    // Keyed by paper only: switching tabs must not remount the reader.
    return <ReaderPage key={route.paperId} paperId={route.paperId} tab={route.tab} target={route.target} />
  }
  return <LibraryPage />
}
