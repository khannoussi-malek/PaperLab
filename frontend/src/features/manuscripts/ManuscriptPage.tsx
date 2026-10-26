import { useManuscript } from '@/api/queries'
import { AppShell } from '@/components/AppShell'
import { LoadError } from '@/features/library/ErrorAlert'
import { TabSkeleton } from '@/features/workspaces/TabStates'
import { workspaceHref } from '@/lib/route'

/** A manuscript's title and files, read-only. The editor replaces this body. */
export function ManuscriptPage({ manuscriptId }: { manuscriptId: string; file: string | null }) {
  const manuscript = useManuscript(manuscriptId)
  const data = manuscript.data
  return (
    <AppShell
      title={data?.title ?? 'Manuscript'}
      back={data?.workspace_id ? { href: workspaceHref(data.workspace_id, 'write'), label: 'Back to workspace' } : undefined}
    >
      {manuscript.error && <LoadError message={manuscript.error.message} onRetry={() => void manuscript.refetch()} />}
      {manuscript.isPending && <TabSkeleton label="Loading manuscript" />}
      {data && (
        <ul className="flex flex-col gap-1 p-3 text-sm">
          {data.files.map((f) => <li key={f.path} className={f.path === data.main_file ? 'font-medium' : undefined}>{f.path}</li>)}
        </ul>
      )}
    </AppShell>
  )
}
