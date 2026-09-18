import { useMemo } from 'react'
import { CHART_INK } from '@/features/charts/palette'
import { FADED, nodeColor } from './graphModel'
import { MISSING_YEARS_HINT, timelineLayout, type TimeAxis } from './timelineModel'
import { useBoxSize } from './useBoxSize'
import type { ViewProps } from './viewModel'

const ARROW = 'timeline-arrow'
const OWN_ARROW = 'timeline-arrow-own'

/**
 * What builds on older work, and where the gaps in time are (spec §5.4): plain SVG over `timelineLayout` (D115).
 * The SVG is aria-hidden like every drawn view; the panel stays the interface. Titles are text children, never markup.
 */
export function TimelineView({ nodes, links, theme, colors, inFocus, onSelect, axis }: ViewProps & { axis: TimeAxis }) {
  const [box, size] = useBoxSize<HTMLDivElement>()
  const layout = useMemo(() => timelineLayout(nodes, links, axis, size), [nodes, links, axis, size])
  const ink = CHART_INK[theme]
  const faded = (...ids: string[]) => inFocus !== null && ids.some((id) => !inFocus.has(id))

  return (
    <div data-view="timeline" className="flex min-h-0 flex-1 flex-col gap-2 p-3">
      <div ref={box} className="relative min-h-[28rem] flex-1">
        {size.width > 0 && (
          <svg aria-hidden width={size.width} height={size.height} className="absolute inset-0">
            <defs>
              {[
                [ARROW, ink.muted],
                [OWN_ARROW, ink.text],
              ].map(([id, fill]) => (
                <marker
                  key={id}
                  id={id}
                  viewBox="0 0 8 8"
                  refX="7"
                  refY="4"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M0,0 L8,4 L0,8 z" fill={fill} />
                </marker>
              ))}
            </defs>
            <line x1={0} x2={size.width} y1={layout.axisY} y2={layout.axisY} stroke={ink.grid} />
            {layout.ticks.map((tick) => (
              <g key={`${tick.label}-${tick.x}`}>
                <line x1={tick.x} x2={tick.x} y1={layout.axisY} y2={layout.axisY + 4} stroke={ink.grid} />
                <text x={tick.x} y={layout.axisY + 18} textAnchor="middle" fontSize={11} fill={ink.muted}>
                  {tick.label}
                </text>
              </g>
            ))}
            {layout.arcs.map((arc) => (
              <path
                key={`${arc.kind}-${arc.source}-${arc.target}`}
                d={arc.path}
                fill="none"
                stroke={arc.kind === 'manual' ? ink.text : ink.muted}
                strokeWidth={arc.kind === 'manual' ? 2.5 : 1}
                strokeOpacity={0.55}
                opacity={faded(arc.source, arc.target) ? FADED : 1}
                markerEnd={
                  arc.kind === 'manual' ? `url(#${OWN_ARROW})` : arc.kind === 'cites' ? `url(#${ARROW})` : undefined
                }
              >
                <title>{arc.title}</title>
              </path>
            ))}
            {layout.dots.map((dot) => (
              <circle
                key={dot.node.id}
                cx={dot.x}
                cy={dot.y}
                r={5}
                fill={nodeColor(dot.node, colors, theme)}
                opacity={faded(dot.node.id) ? FADED : 1}
                className="cursor-pointer"
                onClick={() => onSelect(dot.node.id)}
              >
                <title>{dot.node.title}</title>
              </circle>
            ))}
          </svg>
        )}
      </div>
      {axis === 'published' && layout.hasUnknown && (
        <p className="text-sm text-muted-foreground">{MISSING_YEARS_HINT}</p>
      )}
    </div>
  )
}
