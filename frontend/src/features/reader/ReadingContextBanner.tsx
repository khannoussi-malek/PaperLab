import { useReadingContext } from '@/api/queries'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { workspaceHref } from '@/lib/route'

/** Full width under the toolbar, why this paper is in the reader's survey — every workspace it was pulled into by
 * a systematic search (Review Focus #1: never just one), its screening priority and note. Empty for the common
 * case of a paper never searched for. */
export function ReadingContextBanner({ paperId }: { paperId: string }) {
  const { data } = useReadingContext(paperId)
  if (!data || data.contexts.length === 0) return null

  return (
    <Alert className="reading-context-banner rounded-none border-x-0 border-t-0 px-4 py-2.5">
      <AlertTitle>Why this paper is here</AlertTitle>
      <AlertDescription>
        <ul className="flex flex-col gap-1">
          {data.contexts.map((context) => (
            <li key={context.workspace_id}>
              <a href={workspaceHref(context.workspace_id, 'screening')} className="font-medium hover:underline">
                {context.workspace_name}
              </a>
              {context.priority != null && <> · Priority {context.priority}</>}
              {context.note && <> · {context.note}</>}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  )
}
