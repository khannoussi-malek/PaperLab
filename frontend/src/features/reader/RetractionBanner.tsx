import { TriangleAlert } from 'lucide-react'
import type { Paper } from '@/api/client'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

/** Full width under the toolbar, opaque, never dismissible: reading a retracted paper unknowingly is the failure. */
export function RetractionBanner({ paper }: { paper: Paper }) {
  return (
    <Alert variant="destructive" className="retraction-banner rounded-none border-x-0 border-t-0 px-4 py-2.5">
      <TriangleAlert aria-hidden />
      <AlertTitle>This paper has been retracted</AlertTitle>
      <AlertDescription>
        Check the retraction notice before relying on its findings.
        {paper.doi && (
          <>
            {' '}
            <a
              href={`https://doi.org/${encodeURIComponent(paper.doi)}`}
              target="_blank"
              rel="noreferrer"
              className="text-primary hover:underline"
            >
              doi:{paper.doi}
            </a>
          </>
        )}
      </AlertDescription>
    </Alert>
  )
}
