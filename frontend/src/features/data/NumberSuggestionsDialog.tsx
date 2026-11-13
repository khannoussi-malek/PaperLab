import { useQuery } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api/client'
import { useDatasetMutations } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

type Props = { paperId: string; sectionTitle: string | null; onClose: () => void }

/** A section's numbers as the model found them (D33), each with its quote; Add puts one in the paper's numbers, with
 * the label marked as the model's. Asked once per opening: the model costs time, so nothing refetches by itself. */
export function NumberSuggestionsDialog({ paperId, sectionTitle, onClose }: Props) {
  const found = useQuery({
    queryKey: ['papers', paperId, 'number-suggestions', sectionTitle],
    queryFn: () => api.suggestNumbers(paperId, sectionTitle),
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    retry: false,
  })
  const { addNumber } = useDatasetMutations()
  const [added, setAdded] = useState<Set<number>>(new Set())
  const suggestions = found.data?.suggestions ?? []
  const dropped = found.data?.dropped ?? 0

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-lg')}>
        <DialogHeader>
          <DialogTitle>Numbers in {sectionTitle ?? 'this section'}</DialogTitle>
          <DialogDescription>
            Suggested by AI. Each value is the paper’s own text at its quote; the label is the model’s, and stays marked.
          </DialogDescription>
        </DialogHeader>
        {found.isPending && <p className="text-sm text-muted-foreground">Reading the section…</p>}
        {found.error && (
          <Alert variant="destructive">
            <AlertDescription>{found.error.message}</AlertDescription>
          </Alert>
        )}
        {found.data && suggestions.length === 0 && <p className="text-sm text-muted-foreground">No numbers found in this section.</p>}
        <ul className="grid max-h-[60vh] gap-2 overflow-auto">
          {suggestions.map((s, index) => (
            <li key={`${s.raw}-${s.page}-${index}`} className="grid gap-1 rounded-md border px-3 py-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate font-medium">{s.label}</span>
                <span className="tabular-nums">
                  {s.raw}
                  {s.unit && ` ${s.unit}`}
                </span>
                {added.has(index) ? (
                  <span className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Check aria-hidden className="size-3.5" />
                    Added
                  </span>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    aria-label={`Add ${s.label}`}
                    disabled={addNumber.isPending}
                    onClick={() =>
                      addNumber.mutate(
                        { paperId, number: { label: s.label, raw: s.raw, unit: s.unit, page: s.page, bbox: s.bbox, suggested: true } },
                        { onSuccess: () => setAdded((done) => new Set(done).add(index)) },
                      )
                    }
                  >
                    Add
                  </Button>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                p. {s.page} · “{s.quote}”
              </p>
            </li>
          ))}
        </ul>
        {dropped > 0 && (
          <p className="text-xs text-muted-foreground">
            {dropped} more weren’t kept: PaperLab couldn’t find them in this section exactly as quoted, or they repeated one above.
          </p>
        )}
        {addNumber.error && (
          <Alert variant="destructive">
            <AlertDescription>{addNumber.error.message}</AlertDescription>
          </Alert>
        )}
      </DialogContent>
    </Dialog>
  )
}
