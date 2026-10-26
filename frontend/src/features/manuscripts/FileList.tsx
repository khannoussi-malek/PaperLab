import type { ManuscriptFile } from '@/api/client'
import { cn } from '@/lib/utils'
import { manuscriptHref } from '@/lib/route'

type Props = { manuscriptId: string; files: ManuscriptFile[]; current: string; main: string }

/** The manuscript's files, each a link to `?file=`, so the address always says what is open. */
export function FileList({ manuscriptId, files, current, main }: Props) {
  return (
    <nav aria-label="Files">
      <h2 className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Files</h2>
      <ul className="flex flex-col">
        {files.map((f) => (
          <li key={f.path}>
            <a
              href={manuscriptHref(manuscriptId, f.path)}
              aria-current={f.path === current ? 'page' : undefined}
              title={f.path === main ? `${f.path} (main file)` : f.path}
              className={cn(
                'block truncate rounded-md px-2 py-1 text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50',
                f.path === current && 'bg-muted font-medium',
              )}
            >
              {f.path}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}
