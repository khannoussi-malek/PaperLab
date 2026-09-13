import { LibraryPage } from './features/library/LibraryPage'
import { useRoute } from './lib/route'

export default function App() {
  const route = useRoute()
  // The reader lands in Task 5; until then a paper link shows this.
  if (route.name === 'reader')
    return (
      <p className="p-6">
        Reader coming next. <a href="#/" className="text-primary underline">Back to library</a>
      </p>
    )
  return <LibraryPage />
}
