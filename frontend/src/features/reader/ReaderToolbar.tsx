import { ZoomIn, ZoomOut } from 'lucide-react'
import type { Paper } from '@/api/client'
import { glass } from '@/components/glass'
import { ModeToggle } from '@/components/mode-toggle'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { PaperDetailsDialog } from './PaperDetailsDialog'
import { ZOOM_STEPS } from './zoom'

type Props = {
  paper: Paper | undefined
  zoomIndex: number
  onZoomChange: (index: number) => void
}

export function ReaderToolbar({ paper, zoomIndex, onZoomChange }: Props) {
  const title = paper?.title
  return (
    <header className={cn('col-span-full flex items-center gap-2 border-b border-glass-border px-4 py-2', glass)}>
      <Button variant="ghost" size="sm" asChild>
        <a href="#/">← Library</a>
      </Button>
      <h1 className="mx-2 flex-1 truncate font-heading text-xl font-semibold" title={title}>
        {title ?? 'Loading…'}
      </h1>
      {paper && <PaperDetailsDialog paper={paper} />}
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
