import { useMemo } from 'react'
import { GraphCanvas } from './GraphCanvas'
import { focusedIds } from './graphModel'
import { RINGS_HINT, ringsCentre, ringsLayout, type RingPlace } from './ringsModel'
import type { ViewProps } from './viewModel'

/** How far everything is from one paper (spec §5.5): the 2D canvas, every paper pinned to a ring (D116). */
export function RingsView({ nodes, links, theme, colors, focusId, hops, onSelect }: ViewProps) {
  const centre = useMemo(() => ringsCentre(nodes, links, focusId), [nodes, links, focusId])
  const rings = useMemo(
    () => (centre === null ? new Map<string, RingPlace>() : ringsLayout(nodes, links, centre)),
    [nodes, links, centre]
  )
  // Rings beyond Links out fade, whether the centre is the focused paper or stands in for one.
  const solid = useMemo(() => (centre === null ? null : focusedIds(links, centre, hops)), [links, centre, hops])

  return (
    <>
      {focusId === null && <p className="px-3 pt-2 text-sm text-muted-foreground">{RINGS_HINT}</p>}
      <GraphCanvas
        nodes={nodes}
        links={links}
        theme={theme}
        colors={colors}
        focused={solid}
        onSelect={onSelect}
        rings={rings}
      />
    </>
  )
}
