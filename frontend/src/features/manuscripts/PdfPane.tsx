import { Alert, AlertDescription } from '@/components/ui/alert'
import { api, type ManuscriptDetail } from '@/api/client'
import { PdfPage } from '../reader/PdfPage'
import { usePdfDocument } from '../reader/usePdfDocument'
import { parseCompileErrors, friendlyCompileCode } from './compileErrors'
import { manuscriptErrorMessage } from './errors'

const PAGE_WIDTH_PT = 612
const GUTTERS_PX = 24

type Props = { manuscript: ManuscriptDetail; width: number }

/** The compiled PDF, with the compile's errors above it. The pane's width is the parent's, so loading never moves it. */
export function PdfPane({ manuscript: m, width }: Props) {
  // The URL carries compiled_at, so each compile is fetched again; after a failed compile the last PDF stays shown.
  const url = m.compiled_at && m.compile_status !== 'failed' ? api.manuscriptPdfUrl(m.id, m.compiled_at) : null
  const { doc, error } = usePdfDocument(url)
  const friendly = friendlyCompileCode(m)
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
            {error ?? (m.compile_status === 'running' ? 'Compiling…' : m.compiled_at ? 'Loading the PDF…' : 'No PDF yet. Press Compile.')}
          </p>
        )}
      </div>
    </section>
  )
}
