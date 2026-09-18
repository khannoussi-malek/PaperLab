import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { KIND_LABELS, KINDS, MAX_HOPS, MIN_HOPS, type LegendEntry, type LinkKind } from './graphModel'

const ALL_WORKSPACES = 'all'

type Props = {
  counts: Record<LinkKind, number>
  layers: LinkKind[]
  onToggleLayer: (kind: LinkKind) => void
  workspaces: { id: string; name: string }[]
  workspaceId: string | null
  onWorkspace: (id: string | null) => void
  legend: LegendEntry[]
  hops: number
  onHops: (hops: number) => void
  focused: boolean
}

export function GraphControls({
  counts,
  layers,
  onToggleLayer,
  workspaces,
  workspaceId,
  onWorkspace,
  legend,
  hops,
  onHops,
  focused,
}: Props) {

  return (
    <div className="flex flex-col gap-5">
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 text-sm font-medium">Links</legend>
        {KINDS.map((kind) => (
          <div key={kind} className="flex items-center gap-2">
            <Checkbox id={`layer-${kind}`} checked={layers.includes(kind)} onCheckedChange={() => onToggleLayer(kind)} />
            <Label htmlFor={`layer-${kind}`} className="text-sm font-normal">
              {KIND_LABELS[kind]} <span className="text-muted-foreground">{counts[kind]}</span>
            </Label>
          </div>
        ))}
      </fieldset>

      <div className="flex flex-col gap-2">
        <Label htmlFor="graph-workspace" className="text-sm font-medium">
          Workspace
        </Label>
        <Select
          value={workspaceId ?? ALL_WORKSPACES}
          onValueChange={(value) => onWorkspace(value === ALL_WORKSPACES ? null : value)}
        >
          <SelectTrigger id="graph-workspace" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_WORKSPACES}>Whole library</SelectItem>
            {workspaces.map((workspace) => (
              <SelectItem key={workspace.id} value={workspace.id}>
                {workspace.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {focused && (
        <div className="flex flex-col gap-2">
          <Label htmlFor="graph-hops" className="text-sm font-medium">
            Links out
          </Label>
          <Select value={String(hops)} onValueChange={(value) => onHops(Number(value))}>
            <SelectTrigger id="graph-hops" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Array.from({ length: MAX_HOPS - MIN_HOPS + 1 }, (_, index) => MIN_HOPS + index).map((value) => (
                <SelectItem key={value} value={String(value)}>
                  {value === 1 ? '1 link' : `${value} links`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {legend.length > 0 && (
        <div className="flex flex-col gap-2">
          <h2 className="text-sm font-medium">Colours</h2>
          <ul className="flex flex-col gap-1.5 text-sm text-muted-foreground">
            {legend.map(({ name, color }) => (
              <li key={name} className="flex items-center gap-2">
                <span aria-hidden className="size-3 shrink-0 rounded-full" style={{ backgroundColor: color }} />
                <span className="truncate" title={name}>
                  {name}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
