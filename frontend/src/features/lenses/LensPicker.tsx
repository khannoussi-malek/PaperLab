import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { LensId } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { LensReader } from './useLensReader'

/** The toolbar's lens: a Select of the API's lenses, then ◀ n/N ▶ over the lens's runs (spec §5). */
export function LensPicker({ reader }: { reader: LensReader }) {
  const { lensId, lens, lenses, runCount, runIndex } = reader
  return (
    <div className="flex items-center gap-1">
      <Select value={lensId} onValueChange={(value) => reader.pick(value as LensId)} disabled={lenses.length === 0}>
        <SelectTrigger size="sm" aria-label="Lens" className="w-40">
          <SelectValue placeholder="Lens">{lens?.label}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {lenses.map((option) => (
            <SelectItem key={option.id} value={option.id}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {lensId !== 'full' && runCount > 0 && (
        <>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Previous lens section"
            disabled={runIndex === 0}
            onClick={() => reader.step(-1)}
          >
            <ChevronLeft aria-hidden />
          </Button>
          <span className="lens-step min-w-10 text-center text-sm tabular-nums" aria-live="polite">
            {runIndex + 1}/{runCount}
          </span>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Next lens section"
            disabled={runIndex === runCount - 1}
            onClick={() => reader.step(1)}
          >
            <ChevronRight aria-hidden />
          </Button>
        </>
      )}
    </div>
  )
}
