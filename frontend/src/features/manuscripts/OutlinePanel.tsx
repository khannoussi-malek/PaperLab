import type { OutlineItem } from './outline'
import { manuscriptHref } from '@/lib/route'
import { cn } from '@/lib/utils'

const INDENT = { 1: 'pl-2', 2: 'pl-5', 3: 'pl-8' } as const
const ROW = 'block w-full truncate rounded-md py-1 pr-2 text-left text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50'

type Props = { manuscriptId: string; items: OutlineItem[]; currentFile: string; onJump: (line: number) => void }

/** Headings of the whole manuscript. One in the open file jumps the cursor; one in another file opens that file. */
export function OutlinePanel({ manuscriptId, items, currentFile, onJump }: Props) {
  return (
    <nav aria-label="Outline">
      <h2 className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Outline</h2>
      {items.length === 0 ? (
        <p className="px-2 text-sm text-muted-foreground">No sections yet.</p>
      ) : (
        <ul className="flex flex-col">
          {items.map((item) => (
            <li key={`${item.file}:${item.line}`}>
              {item.file === currentFile ? (
                <button type="button" className={cn(ROW, INDENT[item.level])} onClick={() => onJump(item.line)}>
                  {item.title}
                </button>
              ) : (
                <a href={manuscriptHref(manuscriptId, item.file)} className={cn(ROW, INDENT[item.level])} title={item.file}>
                  {item.title}
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </nav>
  )
}
