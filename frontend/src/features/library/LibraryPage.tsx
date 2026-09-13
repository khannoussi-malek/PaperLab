import { Upload } from 'lucide-react'
import { useRef } from 'react'
import type { Paper } from '@/api/client'
import { useDeletePaper, usePapers, useUploadPapers } from '@/api/queries'
import { ModeToggle } from '@/components/mode-toggle'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table'
import { readerHref } from '@/lib/route'

const STATUS_VARIANT = { ready: 'secondary', failed: 'destructive' } as const
const statusVariant = (status: string) => STATUS_VARIANT[status as keyof typeof STATUS_VARIANT] ?? 'outline'

export function LibraryPage() {
  const papers = usePapers()
  const upload = useUploadPapers()
  const remove = useDeletePaper()
  const fileInput = useRef<HTMLInputElement>(null)

  function onFiles(input: HTMLInputElement) {
    const files = [...(input.files ?? [])]
    input.value = ''
    if (files.length > 0) upload.mutate(files)
  }

  function onDelete(paper: Paper) {
    if (!window.confirm(`Delete "${paper.title}"? Its highlights go with it; notes are kept.`)) return
    remove.mutate(paper.id)
  }

  const error = upload.error ?? remove.error ?? papers.error
  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-4 px-4 py-6">
      <header className="flex items-center justify-between gap-2">
        <h1 className="font-heading text-3xl font-semibold">PaperLab</h1>
        <div className="flex items-center gap-2">
          <Button type="button" disabled={upload.isPending} onClick={() => fileInput.current?.click()}>
            <Upload aria-hidden />
            {upload.isPending ? 'Uploading…' : 'Upload PDFs'}
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept="application/pdf"
            multiple
            hidden
            onChange={(e) => onFiles(e.currentTarget)}
          />
          <ModeToggle />
        </div>
      </header>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      )}

      {papers.data === undefined ? (
        papers.isError ? (
          <Button variant="outline" className="self-start" onClick={() => void papers.refetch()}>
            Retry
          </Button>
        ) : (
          <p className="text-muted-foreground">Loading…</p>
        )
      ) : papers.data.length === 0 ? (
        <p className="text-muted-foreground">No papers yet. Upload a PDF to start.</p>
      ) : (
        <Card className="py-0">
          <Table>
            <TableBody>
              {papers.data.map((paper) => (
                <TableRow key={paper.id} className="paper-row">
                  <TableCell className="whitespace-normal">
                    <a href={readerHref(paper.id)} className="font-medium hover:underline">
                      {paper.title}
                    </a>
                    {paper.status_error && <p className="text-xs text-destructive">{paper.status_error}</p>}
                  </TableCell>
                  <TableCell className="w-0">
                    <Badge variant={statusVariant(paper.status)} className="status">
                      {paper.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="w-0">
                    <Button variant="ghost" size="sm" className="text-destructive" onClick={() => onDelete(paper)}>
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </main>
  )
}
