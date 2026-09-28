import { LoaderCircle } from 'lucide-react'
import { useReferencePage, useRefreshReferences, useWorkspace, useWorkspaces } from '@/api/queries'
import { AppShell } from '@/components/AppShell'
import { delayedIn } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ErrorAlert, LoadError } from '@/features/library/ErrorAlert'
import { readerHref, referencesHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { ReferenceRow } from './ReferenceRow'
import { coverageLine, sectionEmptyText } from './referencesMeta'

function UnfetchedRow({ paper }: { paper: { id: string; title: string; state: string; error: string | null } }) {
  const refresh = useRefreshReferences(paper.id)
  return (
    <li className="unfetched-paper flex items-center gap-3 px-3 py-2">
      <div className="min-w-0 flex-1">
        <a href={readerHref(paper.id)} title={paper.title} className="truncate text-sm">
          {paper.title}
        </a>
        {paper.state === 'failed' && paper.error && <p className="text-xs text-destructive">{paper.error}</p>}
      </div>
      {paper.state === 'fetching' ? (
        <Button variant="outline" size="sm" disabled aria-label={`Fetching references for ${paper.title}`}>
          <LoaderCircle aria-hidden className="motion-safe:animate-spin" />
          Fetching…
        </Button>
      ) : (
        <Button
          variant="outline"
          size="sm"
          aria-label={`${paper.state === 'failed' ? 'Try again' : 'Fetch'} references for ${paper.title}`}
          onClick={() => refresh.mutate()}
        >
          {paper.state === 'failed' ? 'Try again' : 'Fetch'}
        </Button>
      )}
    </li>
  )
}

/** The library's, or one workspace's, References page (D121, D166, D177): To read, and the works several of its
 * papers share. */
export function ReferencesPage({ workspaceId }: { workspaceId: string | null }) {
  const workspaces = useWorkspaces()
  const workspace = useWorkspace(workspaceId ?? '')
  // undefined: still loading (permit it — a fast, likely-cached lookup); null: confirmed gone; only then hold the
  // reference-page query, so an unknown workspace's listing genuinely "isn't asked for" (spec §3.10).
  const known = workspaceId === null || workspace.data != null
  const page = useReferencePage(workspaceId, known)

  function showScope(value: string) {
    window.location.hash = referencesHref(value === 'library' ? null : value) // assign: Back walks back through scopes
  }

  if (workspaceId !== null && workspace.data === null) {
    return (
      <AppShell title="References">
        <div className="flex max-w-3xl flex-col gap-4">
          <ErrorAlert message="That workspace no longer exists." />
          <Button variant="outline" size="sm" asChild className="w-fit">
            <a href={referencesHref()}>Show the whole library</a>
          </Button>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell
      title="References"
      actions={
        <div className="flex items-center gap-2">
          <Label htmlFor="references-workspace" className="text-sm font-medium">
            Workspace
          </Label>
          <Select value={workspaceId ?? 'library'} onValueChange={showScope}>
            <SelectTrigger id="references-workspace" className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="library">Whole library</SelectItem>
              {(workspaces.data ?? []).map((option) => (
                <SelectItem key={option.id} value={option.id}>
                  {option.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      }
    >
      <div className="flex max-w-3xl flex-col gap-6">
        {page.data === undefined ? (
          page.isError ? (
            <LoadError message={page.error.message} onRetry={() => void page.refetch()} />
          ) : (
            <p className={cn('text-muted-foreground', delayedIn)}>Loading references…</p>
          )
        ) : (
          <>
            <section aria-label="Coverage" className="references-coverage flex flex-col gap-2">
              <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
                {coverageLine(page.data.coverage.fetched, page.data.coverage.total, workspaceId !== null)}
              </p>
              {page.data.coverage.unfetched.length > 0 && (
                <>
                  <div>
                    <h2 className="text-sm font-medium">
                      Not looked up yet <span className="tabular-nums text-muted-foreground">({page.data.coverage.unfetched.length})</span>
                    </h2>
                    <p className="text-xs text-muted-foreground">
                      Fetch asks Semantic Scholar, and OpenAlex when it's on, for a paper's references, as its References tab does.
                    </p>
                  </div>
                  <ul className="unfetched-papers max-h-48 divide-y divide-glass-border overflow-y-auto rounded-xl border border-glass-border">
                    {page.data.coverage.unfetched.map((paper) => (
                      <UnfetchedRow key={paper.id} paper={paper} />
                    ))}
                  </ul>
                </>
              )}
            </section>

            <section aria-labelledby="to-read-heading" className="flex flex-col gap-2">
              <h2 id="to-read-heading" tabIndex={-1} className="font-heading text-xl font-semibold">
                To read <span className="tabular-nums text-muted-foreground">({page.data.to_read.length})</span>
              </h2>
              {page.data.to_read.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nothing marked To read. Press To read on a reference, here or in a paper's References tab.</p>
              ) : (
                <ul className="reference-list divide-y divide-glass-border rounded-xl border border-glass-border">
                  {page.data.to_read.map((row) => (
                    <ReferenceRow
                      key={row.id}
                      reference={row}
                      direction="cites"
                      workspaceId={workspaceId ?? undefined}
                      onUnqueued={() => document.getElementById('to-read-heading')?.focus()}
                    />
                  ))}
                </ul>
              )}
            </section>

            <section aria-labelledby="cited-heading" className="flex flex-col gap-2">
              <div>
                <h2 id="cited-heading" className="font-heading text-xl font-semibold">
                  Cited by several of your papers <span className="tabular-nums text-muted-foreground">({page.data.cited_by_several.length})</span>
                </h2>
                <p className="text-sm text-muted-foreground">Works two or more of these papers cite, the most shared first.</p>
              </div>
              {page.data.cited_by_several.length === 0 ? (
                <p className="text-sm text-muted-foreground">{sectionEmptyText('cited', page.data.coverage.fetched)}</p>
              ) : (
                <ul className="reference-list divide-y divide-glass-border rounded-xl border border-glass-border">
                  {page.data.cited_by_several.map((row) => (
                    <ReferenceRow key={row.id} reference={row} direction="cites" workspaceId={workspaceId ?? undefined} />
                  ))}
                </ul>
              )}
            </section>

            <section aria-labelledby="citing-heading" className="flex flex-col gap-2">
              <div>
                <h2 id="citing-heading" className="font-heading text-xl font-semibold">
                  Citing several of your papers <span className="tabular-nums text-muted-foreground">({page.data.citing_several.length})</span>
                </h2>
                <p className="text-sm text-muted-foreground">
                  Works that cite two or more of these papers, newest first. Only the papers looked up so far count, with up to 200 citing works each.
                </p>
              </div>
              {page.data.citing_several.length === 0 ? (
                <p className="text-sm text-muted-foreground">{sectionEmptyText('citing', page.data.coverage.fetched)}</p>
              ) : (
                <ul className="reference-list divide-y divide-glass-border rounded-xl border border-glass-border">
                  {page.data.citing_several.map((row) => (
                    <ReferenceRow key={row.id} reference={row} direction="cited_by" workspaceId={workspaceId ?? undefined} />
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </AppShell>
  )
}
