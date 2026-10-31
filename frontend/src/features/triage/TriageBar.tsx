import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ORDERS, type Order } from './queue'

export const SAVING = 'Saving… try again in a moment'

type Props = {
  sourceLabel: string
  left: number
  total: number
  notReady: number
  /** Papers whose import failed: left out, with a count. */
  failed?: number
  order: Order
  includeDecided: boolean
  onOrder: (order: Order) => void
  onIncludeDecided: (on: boolean) => void
  onExit: () => void
  /** Absent on the done screen, which has its own. */
  onStartOver?: () => void
  canStartOver?: boolean
}

export function TriageBar({ sourceLabel, left, total, notReady, failed = 0, order, includeDecided, onOrder, onIncludeDecided, onExit, onStartOver, canStartOver = true }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <p className="text-sm font-medium">
        Triage · {sourceLabel} · {left} left of {total}
        {notReady > 0 && (
          <span className="font-normal text-muted-foreground">
            {' '}· {notReady} {notReady === 1 ? 'paper is' : 'papers are'} still being read in and not in the stack yet
          </span>
        )}
        {failed > 0 && (
          <span className="font-normal text-muted-foreground">
            {' '}· {failed} {failed === 1 ? 'paper' : 'papers'} couldn't be imported
          </span>
        )}
      </p>
      <div className="ml-auto flex flex-wrap items-center gap-3">
        <Label htmlFor="triage-order" className="sr-only">Order</Label>
        <Select value={order} onValueChange={(v) => onOrder(v as Order)}>
          <SelectTrigger id="triage-order" className="w-48"><SelectValue /></SelectTrigger>
          <SelectContent>
            {ORDERS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2">
          <Switch id="triage-include" checked={includeDecided} onCheckedChange={onIncludeDecided} />
          <Label htmlFor="triage-include">Include decided papers</Label>
        </div>
        {onStartOver && <Button variant="ghost" size="sm" disabled={!canStartOver} title={canStartOver ? undefined : SAVING} onClick={onStartOver}>Start over</Button>}
        <Button variant="outline" size="sm" onClick={onExit}>Exit (Esc)</Button>
      </div>
    </div>
  )
}
