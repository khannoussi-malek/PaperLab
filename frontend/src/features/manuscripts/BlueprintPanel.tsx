import { useQuery } from '@tanstack/react-query'
import { api, type ManuscriptFile } from '@/api/client'
import { BLUEPRINT_PATH, parseBlueprint } from './blueprint'

type Props = { manuscriptId: string; files: ManuscriptFile[] }

/** The paper plan from blueprint.json, read-only. Renders nothing when the file is not there. */
export function BlueprintPanel({ manuscriptId, files }: Props) {
  const present = files.some((f) => f.path === BLUEPRINT_PATH)
  const query = useQuery({
    queryKey: ['manuscripts', manuscriptId, 'file', BLUEPRINT_PATH],
    queryFn: () => api.getManuscriptFile(manuscriptId, BLUEPRINT_PATH),
    enabled: present,
  })
  if (!present) return null
  const plan = query.data ? parseBlueprint(query.data.text) : null
  return (
    <section aria-label="Paper plan">
      <h2 className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Paper plan</h2>
      {query.isError || (query.data && !plan) ? (
        <p className="px-2 text-xs text-muted-foreground">{BLUEPRINT_PATH} can't be read. Open it in All files to fix it.</p>
      ) : plan && (
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
        </div>
      )}
    </section>
  )
}
