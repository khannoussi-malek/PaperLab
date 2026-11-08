import { useCallback, useState } from 'react'
import { Button } from '@/components/ui/button'

export type ViewKind = 'tree' | 'radial' | 'map' | 'outline'
const VIEWS: [ViewKind, string][] = [['tree', 'Tree'], ['radial', 'Radial'], ['map', 'Map'], ['outline', 'Outline']]
const keyFor = (workspaceId: string) => `snowball-tree-view:${workspaceId}`

function read(workspaceId: string): ViewKind {
  try {
    const v = localStorage.getItem(keyFor(workspaceId))
    return VIEWS.some(([k]) => k === v) ? (v as ViewKind) : 'tree'
  } catch {
    return 'tree'
  }
}

/** The chosen view, remembered per workspace; storage that fails just means Tree next time. */
export function useStoredView(workspaceId: string) {
  const [view, setView] = useState(() => read(workspaceId))
  const choose = useCallback((next: ViewKind) => {
    setView(next)
    try { localStorage.setItem(keyFor(workspaceId), next) } catch { /* ponytail: not remembered, still switches */ }
  }, [workspaceId])
  return [view, choose] as const
}

export function ViewSwitch({ value, onChange }: { value: ViewKind; onChange: (v: ViewKind) => void }) {
  return (
    <div role="group" aria-label="View" className="flex gap-1">
      {VIEWS.map(([k, label]) => (
        <Button key={k} type="button" size="sm" variant={value === k ? 'default' : 'outline'} aria-pressed={value === k} onClick={() => onChange(k)}>
          {label}
        </Button>
      ))}
    </div>
  )
}
