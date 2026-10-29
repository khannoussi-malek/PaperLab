import { useMissingKeys } from '@/api/queries'

const CAP = 20

type Props = { manuscriptId: string; compiledAt: string | null | undefined; onJump: (file: string, line: number) => void }

export function MissingCites({ manuscriptId, compiledAt, onJump }: Props) {
  const { data } = useMissingKeys(manuscriptId, compiledAt)
  if (!data?.length) return null
  const more = data.length - CAP
  return (
    <section aria-label="Cited but not found" className="max-h-40 shrink-0 overflow-auto border-t border-border bg-card/60 px-3 py-2 backdrop-blur">
      <h3 className="text-sm font-medium">Cited but not found</h3>
      <p className="text-xs text-muted-foreground">These keys match no paper in your library or your .bib files, so LaTeX prints [?].</p>
      <ul className="mt-1 space-y-0.5">
        {data.slice(0, CAP).map((m, i) => (
          <li key={`${m.key}-${m.file}-${m.line}-${i}`}>
            <button type="button" onClick={() => onJump(m.file, m.line)}
              className="flex w-full items-baseline justify-between gap-3 rounded px-1 py-0.5 text-left text-sm hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <span className="font-mono">{m.key}</span>
              <span className="text-xs text-muted-foreground">{m.file}:{m.line}</span>
            </button>
          </li>
        ))}
      </ul>
      {more > 0 && <p className="mt-1 text-xs text-muted-foreground">and {more} more</p>}
    </section>
  )
}
