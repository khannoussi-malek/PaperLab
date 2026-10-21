import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { keys, useFoundPdfs, useMarkFoundPdfsSeen } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { readerHref } from '@/lib/route'

/** Free copies the weekly re-check turned up: titles linked, and Dismiss marks exactly the ones shown as seen. */
export function FoundPdfsNotice() {
  const found = useFoundPdfs()
  const seen = useMarkFoundPdfsSeen()
  const client = useQueryClient()
  const list = found.data ?? []
  const shown = useRef<number | null>(null) // null until the first list: that one is not news
  useEffect(() => {
    if (!found.data) return
    // a new find upgraded a paper: the library behind the notice drops its "No PDF yet" badge
    if (shown.current !== null && found.data.length > shown.current) void client.invalidateQueries({ queryKey: keys.papers })
    shown.current = found.data.length
  }, [found.data, client])
  if (list.length === 0) return null
  return (
    <div role="status" className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
      <span>Found free PDFs for {list.length} {list.length === 1 ? 'paper' : 'papers'} saved without one:</span>
      <ul className="flex flex-wrap gap-x-3">
        {list.map((f) => (
          <li key={f.id}>
            <a href={readerHref(f.paper_id)} className="text-primary hover:underline">{f.title}</a>
          </li>
        ))}
      </ul>
      <Button variant="ghost" size="sm" disabled={seen.isPending} onClick={() => seen.mutate(list.map((f) => f.id))}>
        Dismiss
      </Button>
      {seen.error && (
        <Alert variant="destructive" className="basis-full border-glass-border">
          <AlertDescription>{seen.error.message}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
