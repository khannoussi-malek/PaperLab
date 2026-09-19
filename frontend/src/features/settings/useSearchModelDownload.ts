import { useSyncExternalStore } from 'react'
import { api, errorDetail, type DownloadDoneEvent, type DownloadErrorEvent, type DownloadProgressEvent } from '@/api/client'
import { useInvalidateEmbedding } from '@/api/queries'
import { readSse } from '@/features/chat/sse'
import { refusedDownload, type DownloadState } from './searchModel'

// One download per tab, shared by every Download button (Settings, the library notice, chat), so each shows the same
// progress. Unlike an Ollama pull, leaving a page doesn't stop it: the download belongs to the app, not the button.
let current: DownloadState = { status: 'idle' }
const listeners = new Set<() => void>()

function publish(next: DownloadState) {
  current = next
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => void listeners.delete(listener)
}

async function download(onFinished: () => void) {
  publish({ status: 'downloading', completed: 0, total: 0 })
  try {
    const response = await api.downloadSearchModel()
    if (!response.ok || !response.body) return publish(refusedDownload(await errorDetail(response)))
    for await (const { event, data } of readSse(response.body)) {
      if (event === 'progress') {
        const { completed, total } = JSON.parse(data) as DownloadProgressEvent
        publish({ status: 'downloading', completed, total })
      }
      if (event === 'error') return publish({ status: 'error', message: (JSON.parse(data) as DownloadErrorEvent).detail })
      if (event === 'done') return publish({ status: 'done', papersQueued: (JSON.parse(data) as DownloadDoneEvent).papers_queued })
    }
    publish({ status: 'error', message: 'The download stopped before it finished.' })
  } catch (error) {
    console.warn('search model download stream failed', error)
    publish({ status: 'error', message: "Can't reach the PaperLab API." })
  } finally {
    onFinished() // GET /api/embedding again: the model, what is left to download, the library notice
  }
}

/** The built-in search model's download in this tab, and a way to start it (a no-op while one runs). */
export function useSearchModelDownload() {
  const state = useSyncExternalStore(subscribe, () => current)
  const invalidateEmbedding = useInvalidateEmbedding()
  const start = () => {
    if (current.status !== 'downloading') void download(invalidateEmbedding)
  }
  return { state, start }
}
