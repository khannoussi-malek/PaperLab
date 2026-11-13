import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { sileo } from 'sileo'
import { api, isConflict, type ManuscriptFile } from '@/api/client'
import { useManuscriptTemplates } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { BLUEPRINT_PATH, latexTitle, parseBlueprint, starterBlueprint } from './blueprint'

type Props = { manuscriptId: string; files: ManuscriptFile[]; mainFile: string; title: string; template: string }

/**
 * The paper plan from blueprint.json. Read-only, except the Create button when there is no file yet:
 * it writes the starter once and never overwrites one.
 */
export function BlueprintPanel({ manuscriptId, files, mainFile, title, template }: Props) {
  const queryClient = useQueryClient()
  const present = files.some((f) => f.path === BLUEPRINT_PATH)
  const query = useQuery({
    queryKey: ['manuscripts', manuscriptId, 'file', BLUEPRINT_PATH],
    queryFn: () => api.getManuscriptFile(manuscriptId, BLUEPRINT_PATH),
    enabled: present,
  })
  const templates = useManuscriptTemplates()
  const bands = templates.data?.find((t) => t.name === template)?.section_words
  const create = useMutation({
    mutationFn: async () => {
      const main = files.some((f) => f.path === mainFile) ? await api.getManuscriptFile(manuscriptId, mainFile) : null
      const plainTitle = (main && latexTitle(main.text)) || title // the paper's \title, else the stored name
      return api.saveManuscriptFile(manuscriptId, BLUEPRINT_PATH, starterBlueprint(plainTitle, bands), null)
    },
    onError: (e) => {
      if (!isConflict(e, 'file_exists')) sileo.error({ title: "Couldn't create the blueprint" }) // already there: the refresh shows it
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ['manuscripts', manuscriptId, 'file', BLUEPRINT_PATH] })
      void queryClient.invalidateQueries({ queryKey: ['manuscripts', manuscriptId] })
    },
  })
  const plan = present && query.data ? parseBlueprint(query.data.text) : null
  const unreadable = present && (query.isError || (query.data !== undefined && plan === null))
  return (
    <section aria-label="Paper plan">
      <h2 className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Paper plan</h2>
      {!present && (
        <div className="flex items-center gap-2 px-2">
          <p className="text-xs text-muted-foreground">No paper plan yet.</p>
          <Button size="xs" variant="outline" disabled={!templates.isSuccess || create.isPending} onClick={() => create.mutate()}>
            Create blueprint
          </Button>
        </div>
      )}
      {unreadable && (
        <p className="px-2 text-xs text-muted-foreground">{BLUEPRINT_PATH} can't be read. Open it in All files to fix it.</p>
      )}
      {plan && (
        <div className="flex flex-col gap-2 px-2 text-sm">
          {plan.title && <p className="font-medium">{plan.title}</p>}
          {plan.contributions.length > 0 && (
            <ol className="list-decimal pl-5">{plan.contributions.map((c, i) => <li key={i}>{c}</li>)}</ol>
          )}
          {plan.notation.length > 0 && (
            <dl className="flex flex-col gap-1">
              {plan.notation.map((n, i) => (
                <div key={i} className="flex gap-2">
                  <dt><code>{n.symbol}</code></dt>
                  <dd>{n.meaning}</dd>
                </div>
              ))}
            </dl>
          )}
          {plan.targets.length > 0 && (
            <ul className="flex flex-col gap-0.5">
              {plan.targets.map((t) => <li key={t.id}>{`${t.id}: ${t.min} to ${t.max} words`}</li>)}
            </ul>
          )}
          {plan.targets.length === 0 && templates.isSuccess && (bands === undefined || Object.keys(bands).length === 0) && (
            <p className="text-xs text-muted-foreground">No word targets yet: this template has none. Add them under target_words.</p>
          )}
        </div>
      )}
    </section>
  )
}
