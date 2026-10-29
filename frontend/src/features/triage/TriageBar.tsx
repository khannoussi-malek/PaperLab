import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ORDERS, type Order } from './queue'

type Props = {
  sourceLabel: string
  left: number
  total: number
  notReady: number
  order: Order
  includeDecided: boolean
  onOrder: (order: Order) => void
  onIncludeDecided: (on: boolean) => void
  onExit: () => void
  /** Absent on the done screen, which has its own. */
  onStartOver?: () => void
}

export function TriageBar({ sourceLabel, left, total, notReady, order, includeDecided, onOrder, onIncludeDecided, onExit, onStartOver }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <p className="text-sm font-medium">
        Triage · {sourceLabel} · {left} left of {total}
        {notReady > 0 && (
          <span className="font-normal text-muted-foreground">
            {' '}· {notReady} {notReady === 1 ? 'paper is' : 'papers are'} still being read in and not in the stack yet
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
        {onStartOver && <Button variant="ghost" size="sm" onClick={onStartOver}>Start over</Button>}
        <Button variant="outline" size="sm" onClick={onExit}>Exit (Esc)</Button>
      </div>
    </div>
  )
}
