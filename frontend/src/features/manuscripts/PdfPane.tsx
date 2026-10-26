import { useRef } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { api, type ManuscriptDetail } from '@/api/client'
import { PdfPage } from '../reader/PdfPage'
import { usePdfDocument } from '../reader/usePdfDocument'
import { parseCompileErrors } from './compileErrors'
import { manuscriptErrorMessage } from './errors'

const PAGE_WIDTH_PT = 612
const GUTTERS_PX = 24

type Props = { manuscript: ManuscriptDetail; width: number }

/** The compiled PDF, with the compile's errors above it. The pane's width is the parent's, so loading never moves it. */
export function PdfPane({ manuscript: m, width }: Props) {
  // The URL carries compiled_at, so each good compile is fetched again. A failed compile also stamps compiled_at but
  // leaves the last PDF on disk, so the URL keeps the last good stamp and that PDF stays on screen.
  const goodAt = useRef<string | null>(null)
  if (m.compile_status === 'ok' && m.compiled_at) goodAt.current = m.compiled_at
  const stamp = goodAt.current ?? m.compiled_at
  const { doc, error } = usePdfDocument(stamp ? api.manuscriptPdfUrl(m.id, stamp) : null)
  const friendly = m.compile_status === 'failed' ? m.compile_friendly : null
  const errors = parseCompileErrors(m.compile_errors).filter((e) => e.kind === 'error')
  const scale = Math.max(0.4, (width - GUTTERS_PX) / PAGE_WIDTH_PT)

  return (
    <section aria-label="PDF preview" className="flex h-full min-h-0 flex-col">
      {m.compile_status === 'failed' && (
        <Alert variant="destructive" className="m-2 w-auto">
          <AlertDescription>
            {friendly ? (
              manuscriptErrorMessage(friendly)
            ) : errors.length > 0 ? (
              <ul className="flex flex-col gap-1">
                {errors.map((e, i) => (
                  <li key={i}>{e.file}{e.line ? `:${e.line}` : ''} {e.message}</li>
                ))}
              </ul>
            ) : (
              'The compile failed.'
            )}
            {m.compile_log && !friendly && (
              <details className="mt-2"><summary className="cursor-pointer">Log</summary><pre className="max-h-48 overflow-auto text-xs whitespace-pre-wrap">{m.compile_log}</pre></details>
            )}
          </AlertDescription>
        </Alert>
      )}
      <div className="min-h-0 flex-1 overflow-auto bg-muted/40 p-3" tabIndex={0} aria-label="PDF pages">
        {doc ? (
          <div className="flex flex-col items-center gap-3">
            {Array.from({ length: doc.numPages }, (_, i) => i + 1).map((n) => <PdfPage key={n} doc={doc} pageNumber={n} scale={scale} />)}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {(m.compile_status === 'failed' ? null : error) ?? (m.compile_status === 'running' ? 'Compiling…' : m.compile_status === 'failed' ? 'No PDF yet. Fix the errors and compile again.' : m.compiled_at ? 'Loading the PDF…' : 'No PDF yet. Press Compile.')}
          </p>
        )}
      </div>
    </section>
  )
}
