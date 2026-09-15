import type { KeyboardEvent } from 'react'
import { pressable } from '@/components/motion'
import { cn } from '@/lib/utils'
import { TYPE_GROUPS, type ChartType } from './builderSpec'
import { TYPE_ICON } from './typeIcons'

/** Why a type can't draw the chart's data, for a disabled chip's `title`. */
const NEEDS: Record<ChartType, string> = {
  bar: 'Needs a number column.',
  line: 'Needs a number column.',
  scatter: 'Needs a number column.',
  box: 'Needs a number column.',
  scatter3d: 'Needs a number column.',
  heatmap: 'Needs a column of row labels and a number column.',
  surface: 'Needs three number columns, for X, Y and Z.',
  contour: 'Needs three number columns, for X, Y and Z.',
  parcoords: 'Needs at least two number columns.',
}

type Props = {
  value: ChartType
  /** Whether a type can draw the current data. */
  enabled: (type: ChartType) => boolean
  onChange: (type: ChartType) => void
}

/** The chart types as toggle chips in three radio groups; arrow keys move within a group. */
export function ChartTypePicker({ value, enabled, onChange }: Props) {
  function move(event: KeyboardEvent<HTMLDivElement>) {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key]
    if (!step) return
    event.preventDefault()
    const chips = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]')]
    const next = chips[(chips.indexOf(event.target as HTMLButtonElement) + step + chips.length) % chips.length]
    next.focus()
    next.click()
  }

  return (
    <div className="grid gap-3">
      {TYPE_GROUPS.map((group) => {
        const inGroup = group.types.some((t) => t.type === value)
        return (
          <div key={group.label} className="grid gap-1.5">
            <span aria-hidden className="text-xs text-muted-foreground">
              {group.label}
            </span>
            <div role="radiogroup" aria-label={group.label} className="flex flex-wrap gap-1.5" onKeyDown={move}>
              {group.types.map(({ type, name }, i) => {
                const Icon = TYPE_ICON[type]
                const checked = type === value
                const disabled = !enabled(type)
                return (
                  <button
                    key={type}
                    type="button"
                    role="radio"
                    aria-checked={checked}
                    aria-disabled={disabled || undefined}
                    title={disabled ? NEEDS[type] : undefined}
                    // Roving focus: one tab stop per group, on its chosen chip (or its first).
                    tabIndex={checked || (!inGroup && i === 0) ? 0 : -1}
                    onClick={() => !disabled && onChange(type)}
                    className={cn(
                      'inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-full px-3 text-sm ring-1 transition-[color,background-color,scale] outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
                      pressable,
                      checked ? 'bg-primary/10 font-medium text-foreground ring-primary' : 'text-muted-foreground ring-border hover:bg-muted',
                      disabled && 'cursor-not-allowed opacity-50 hover:bg-transparent',
                    )}
                  >
                    <Icon aria-hidden className="size-4" />
                    {name}
                  </button>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
