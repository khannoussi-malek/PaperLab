import type { CheckFinding } from '@/api/client'
import { cn } from '@/lib/utils'
import type { Severity } from './model'

const DOT: Record<Severity, string> = { error: 'bg-destructive', warning: 'bg-amber-500', info: 'bg-muted-foreground' }
const ROW = 'flex w-full items-baseline justify-between gap-3 rounded px-1 py-0.5 text-left text-sm'

export function FindingRow({ finding: x, onJump }: { finding: CheckFinding; onJump: (file: string, line: number) => void }) {
  const inner = (
    <>
      <span className="flex items-baseline gap-1.5">
        <span aria-hidden className={cn('size-1.5 shrink-0 rounded-full', DOT[x.severity])} />
        <span className="text-xs text-muted-foreground">{x.severity}</span>
        <span>{x.message}</span>
      </span>
      {x.file != null && x.line != null && <span className="shrink-0 text-xs text-muted-foreground">{x.file}:{x.line}</span>}
    </>
  )
  const { file, line } = x
  return (
    <li>
      {file != null && line != null ? (
        <button type="button" onClick={() => onJump(file, line)}
          className={cn(ROW, 'hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring')}>{inner}</button>
      ) : <div className={ROW}>{inner}</div>}
      {x.fix_hint && <p className="pl-4 text-xs text-muted-foreground">{x.fix_hint}</p>}
    </li>
  )
}
