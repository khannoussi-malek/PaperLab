import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { keys, useFoundPdfs, useMarkFoundPdfsSeen } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { readerHref } from '@/lib/route'

function FoundLink({ found }: { found: { paper_id: string; title: string } }) {
  return <a href={readerHref(found.paper_id)} className="text-primary hover:underline">{found.title}</a>
}

/**
 * Free copies the weekly re-check turned up. One summary line; with several papers a Show toggle lists
 * the titles below it. Dismiss marks exactly the ones shown as seen.
 */
export function FoundPdfsNotice() {
  const found = useFoundPdfs()
  const seen = useMarkFoundPdfsSeen()
  const client = useQueryClient()
  const list = found.data ?? []
  const shown = useRef<number | null>(null) // null until the first list: that one is not news
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!found.data) return
    // a new find upgraded a paper: the library behind the notice drops its "No PDF yet" badge
    if (shown.current !== null && found.data.length > shown.current) void client.invalidateQueries({ queryKey: keys.papers })
    shown.current = found.data.length
  }, [found.data, client])
  if (list.length === 0) return null
  const single = list.length === 1 ? list[0] : undefined
  return (
    <div role="status" className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
      {single ? (
        <span>Found a free PDF for &quot;<FoundLink found={single} />&quot;.</span>
      ) : (
        <>
          <span>{`Found free PDFs for ${list.length} papers saved without one.`}</span>
          <Button variant="ghost" size="sm" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? 'Hide' : 'Show'}
          </Button>
        </>
      )}
      <Button variant="ghost" size="sm" disabled={seen.isPending} onClick={() => seen.mutate(list.map((f) => f.id))}>
        Dismiss
      </Button>
      {!single && open && (
        <ul className="flex basis-full flex-col gap-1">
          {list.map((f) => (
            <li key={f.id}>
              <FoundLink found={f} />
            </li>
          ))}
        </ul>
      )}
      {seen.error && (
        <Alert variant="destructive" className="basis-full border-glass-border">
          <AlertDescription>{seen.error.message}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
