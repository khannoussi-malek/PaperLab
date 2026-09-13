import { ZoomIn, ZoomOut } from 'lucide-react'
import { ModeToggle } from '@/components/mode-toggle'
import { Button } from '@/components/ui/button'
import { ZOOM_STEPS } from './zoom'

type Props = {
  title: string | undefined
  zoomIndex: number
  onZoomChange: (index: number) => void
}

export function ReaderToolbar({ title, zoomIndex, onZoomChange }: Props) {
  return (
    <header className="col-span-full flex items-center gap-2 border-b bg-card px-4 py-2">
      <Button variant="ghost" size="sm" asChild>
        <a href="#/">← Library</a>
      </Button>
      <h1 className="mx-2 flex-1 truncate font-heading text-xl font-semibold" title={title}>
        {title ?? 'Loading…'}
      </h1>
      <Button
        variant="outline"
        size="icon"
        aria-label="Zoom out"
        disabled={zoomIndex === 0}
        onClick={() => onZoomChange(Math.max(0, zoomIndex - 1))}
      >
        <ZoomOut aria-hidden />
      </Button>
      <span className="zoom-level min-w-14 text-center text-sm tabular-nums">
        {Math.round(ZOOM_STEPS[zoomIndex] * 100)}%
      </span>
      <Button
        variant="outline"
        size="icon"
        aria-label="Zoom in"
        disabled={zoomIndex === ZOOM_STEPS.length - 1}
        onClick={() => onZoomChange(Math.min(ZOOM_STEPS.length - 1, zoomIndex + 1))}
      >
        <ZoomIn aria-hidden />
      </Button>
      <ModeToggle />
    </header>
  )
}
