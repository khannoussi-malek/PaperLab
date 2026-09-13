import { LibraryPage } from './features/library/LibraryPage'
import { ReaderPage } from './features/reader/ReaderPage'
import { useRoute } from './lib/route'

export default function App() {
  const route = useRoute()
  return route.name === 'reader' ? <ReaderPage key={route.paperId} paperId={route.paperId} /> : <LibraryPage />
}
