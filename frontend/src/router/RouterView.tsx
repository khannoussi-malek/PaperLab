import type { ReactNode } from 'react'
import { useOpenSetupOnStart } from '@/features/setup/useOpenSetupOnStart'
import { lazyPage } from './lazyPage'
import { useRoute, type Route } from './route'

// Each page is its own chunk, loaded the first time its route opens.
const LibraryPage = lazyPage(() => import('@/features/library/LibraryPage').then((m) => m.LibraryPage))
const ReaderPage = lazyPage(() => import('@/features/reader/ReaderPage').then((m) => m.ReaderPage), { bare: true })
const WorkspacePage = lazyPage(() => import('@/features/workspaces/WorkspacePage').then((m) => m.WorkspacePage))
const ManuscriptPage = lazyPage(() => import('@/features/manuscripts/ManuscriptPage').then((m) => m.ManuscriptPage))
const ChartsPage = lazyPage(() => import('@/features/charts/ChartsPage').then((m) => m.ChartsPage))
const ChartPage = lazyPage(() => import('@/features/charts/ChartPage').then((m) => m.ChartPage))
const ChartBuilderPage = lazyPage(() => import('@/features/charts/ChartBuilderPage').then((m) => m.ChartBuilderPage))
const DatasetPage = lazyPage(() => import('@/features/data/DatasetPage').then((m) => m.DatasetPage))
const SettingsPage = lazyPage(() => import('@/features/settings/SettingsPage').then((m) => m.SettingsPage))
const ConnectClaudePage = lazyPage(() => import('@/features/connect-claude/ConnectClaudePage').then((m) => m.ConnectClaudePage))
const SetupPage = lazyPage(() => import('@/features/setup/SetupPage').then((m) => m.SetupPage), { bare: true })
const NotesPage = lazyPage(() => import('@/features/notes/NotesPage.tsx').then((m) => m.NotesPage))
const ReferencesPage = lazyPage(() => import('@/features/references/ReferencesPage').then((m) => m.ReferencesPage))
const GraphPage = lazyPage(() => import('@/features/graph/GraphPage').then((m) => m.GraphPage))

type RouteOf<N extends Route['name']> = Extract<Route, { name: N }>

/** What each route shows. A `key` remounts the page when that id changes; tabs and targets never remount it. */
const pages: { [N in Route['name']]: (route: RouteOf<N>) => ReactNode } = {
  library: () => <LibraryPage />,
  workspace: (r) => <WorkspacePage key={r.workspaceId} workspaceId={r.workspaceId} tab={r.tab} runId={r.runId} tags={r.tags} match={r.match} />,
  reader: (r) => <ReaderPage key={r.paperId} paperId={r.paperId} tab={r.tab} target={r.target} />,
  manuscript: (r) => <ManuscriptPage key={r.manuscriptId} manuscriptId={r.manuscriptId} file={r.file} line={r.line} />,
  charts: () => <ChartsPage />,
  'chart-builder': (r) => (
    <ChartBuilderPage key={r.chartId ?? `new-${r.datasetId ?? ''}`} chartId={r.chartId} datasetId={r.datasetId} />
  ),
  chart: (r) => <ChartPage key={r.chartId} chartId={r.chartId} />,
  dataset: (r) => <DatasetPage key={r.datasetId} datasetId={r.datasetId} focus={r.focus} />,
  settings: () => <SettingsPage />,
  'connect-claude': () => <ConnectClaudePage />,
  setup: () => <SetupPage />,
  notes: (r) => <NotesPage paper={r.paper} />,
  references: (r) => <ReferencesPage workspaceId={r.workspaceId} />,
  graph: () => <GraphPage />,
}

/** The page for the current hash. */
export function RouterView() {
  const route = useRoute()
  useOpenSetupOnStart()
  // TS can't tie `pages[route.name]` to `route`'s own member of the union; the mapped type above already does.
  const render = pages[route.name] as (route: Route) => ReactNode
  return render(route)
}
