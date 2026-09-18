import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { GraphCanvas } from './GraphCanvas'
import { MatrixView } from './MatrixView'
import { TimelineView } from './TimelineView'
import type { TimeAxis } from './timelineModel'
import { isGraphView, VIEW_LABELS, VIEWS, type GraphView, type ViewProps } from './viewModel'

type Props = ViewProps & {
  view: GraphView
  onView: (view: GraphView) => void
  /** The Timeline's axis; the select lives in the controls column. */
  axis: TimeAxis
}

/**
 * The switcher over the middle column (spec §4). Radix renders only the chosen tab's content, so a view that was
 * never picked loads nothing, and every view gets the same props (D113).
 */
export function GraphViews({ view, onView, axis, ...shared }: Props) {
  return (
    <Tabs
      value={view}
      onValueChange={(value) => {
        if (isGraphView(value)) onView(value)
      }}
      className="min-h-0 flex-1"
    >
      <TabsList aria-label="Graph view" className="mx-3 mt-3">
        {VIEWS.map((option) => (
          <TabsTrigger key={option} value={option}>
            {VIEW_LABELS[option]}
          </TabsTrigger>
        ))}
      </TabsList>
      <TabsContent value="2d" className="flex min-h-0 flex-col">
        <GraphCanvas
          nodes={shared.nodes}
          links={shared.links}
          theme={shared.theme}
          colors={shared.colors}
          focused={shared.inFocus}
          onSelect={shared.onSelect}
        />
      </TabsContent>
      <TabsContent value="matrix" className="flex min-h-0 flex-col">
        <MatrixView {...shared} />
      </TabsContent>
      <TabsContent value="timeline" className="flex min-h-0 flex-col">
        <TimelineView {...shared} axis={axis} />
      </TabsContent>
    </Tabs>
  )
}
