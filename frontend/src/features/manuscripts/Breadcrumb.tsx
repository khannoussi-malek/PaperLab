import type { OutlineItem } from './outline'

/** Where the cursor is, section › subsection; each crumb jumps there. Empty before the first heading. */
export function Breadcrumb({ crumbs, onJump }: { crumbs: OutlineItem[]; onJump: (file: string, line: number) => void }) {
  return (
    <nav aria-label="Where you are" className="flex h-7 shrink-0 items-center gap-1 overflow-hidden border-b border-glass-border px-3 text-xs text-muted-foreground">
      {crumbs.length === 0 && <span>Start of the paper</span>}
      {crumbs.map((c, i) => (
        <span key={`${c.file}:${c.line}`} className="flex min-w-0 items-center gap-1">
          {i > 0 && <span aria-hidden>›</span>}
          <button type="button" onClick={() => onJump(c.file, c.line)} aria-current={i === crumbs.length - 1 ? 'location' : undefined}
            className="min-w-0 truncate rounded px-1 outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
            {c.title}
          </button>
        </span>
      ))}
    </nav>
  )
}
