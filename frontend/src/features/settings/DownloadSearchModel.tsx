import { Download } from 'lucide-react'
import { useEmbeddingStatus } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Scene3D } from '@/features/scene3d/Scene3D'
import { downloadLabel, downloadPercent, statusLine } from './searchModel'
import { useSearchModelDownload } from './useSearchModelDownload'

// Module level, so the scene never restarts on a re-render.
const loadDownloadScene = () => import('@/features/scene3d/directors/download')

/**
 * The built-in search model's Download button, then the download's progress bar and status line, or its error. The
 * same download wherever it shows (Settings → Search, the library notice, chat). `alwaysShowStatus`: show the status
 * line before any download too (Settings); elsewhere it appears once a download starts. `scene`: show the 3D
 * download moment above the status (Settings → Search and Setup); elsewhere the plain bar is enough.
 */
export function DownloadSearchModel({ alwaysShowStatus = false, scene = false }: { alwaysShowStatus?: boolean; scene?: boolean }) {
  const status = useEmbeddingStatus()
  const { state, start } = useSearchModelDownload()
  if (status.data === undefined) return null
  const present = status.data.model_present
  const percent = state.status === 'downloading' ? downloadPercent(state) : state.status === 'done' || present ? 100 : 0
  return (
    <div className="flex flex-col gap-2">
      {scene && <Scene3D load={loadDownloadScene} input={{ status: present && state.status === 'idle' ? 'ready' : state.status, percent }} className="h-40 w-full max-w-sm" />}
      {(alwaysShowStatus || state.status !== 'idle') && (
        <p className="search-model-status text-sm tabular-nums text-muted-foreground">{statusLine(present, state)}</p>
      )}
      {state.status === 'downloading' && (
        <Progress aria-label="Downloading the search model" value={downloadPercent(state)} />
      )}
      {!present && (state.status === 'idle' || state.status === 'error') && (
        <div>
          <Button variant="outline" size="sm" onClick={start}>
            <Download aria-hidden />
            {downloadLabel(status.data.download_bytes)}
          </Button>
        </div>
      )}
      {state.status === 'error' && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{state.message}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
