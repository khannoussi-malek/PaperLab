import type { ReactNode } from 'react'
import { useOpenSetupOnStart } from '@/features/setup/useOpenSetupOnStart'
import { lazyPage } from './lazyPage'
import { loadPagesWith, useRoute, type Route } from './route'

// Each page is its own chunk, loaded the first time its route opens.
const LibraryPage = lazyPage(() => import('@/pages/LibraryPage').then((m) => m.LibraryPage))
const ReaderPage = lazyPage(() => import('@/pages/ReaderPage').then((m) => m.ReaderPage), { bare: true })
const WorkspacePage = lazyPage(() => import('@/pages/WorkspacePage').then((m) => m.WorkspacePage))
const ManuscriptPage = lazyPage(() => import('@/pages/ManuscriptPage').then((m) => m.ManuscriptPage))
const ChartsPage = lazyPage(() => import('@/pages/ChartsPage').then((m) => m.ChartsPage))
const ChartPage = lazyPage(() => import('@/pages/ChartPage').then((m) => m.ChartPage))
const ChartBuilderPage = lazyPage(() => import('@/pages/ChartBuilderPage').then((m) => m.ChartBuilderPage))
const DatasetPage = lazyPage(() => import('@/pages/DatasetPage').then((m) => m.DatasetPage))
const SettingsPage = lazyPage(() => import('@/pages/SettingsPage').then((m) => m.SettingsPage))
const ConnectClaudePage = lazyPage(() => import('@/pages/ConnectClaudePage').then((m) => m.ConnectClaudePage))
const SetupPage = lazyPage(() => import('@/pages/SetupPage').then((m) => m.SetupPage), { bare: true })
const NotesPage = lazyPage(() => import('@/pages/NotesPage').then((m) => m.NotesPage))
const ReferencesPage = lazyPage(() => import('@/pages/ReferencesPage').then((m) => m.ReferencesPage))
const GraphPage = lazyPage(() => import('@/pages/GraphPage').then((m) => m.GraphPage))

// The code each route needs, fetched before a navigation's fade so the fade shows the page, not its Loading….
const pageCode: { [N in Route['name']]: { preload: () => Promise<unknown> } } = {
  library: LibraryPage,
  workspace: WorkspacePage,
  reader: ReaderPage,
  manuscript: ManuscriptPage,
  charts: ChartsPage,
  'chart-builder': ChartBuilderPage,
  chart: ChartPage,
  dataset: DatasetPage,
  settings: SettingsPage,
  'connect-claude': ConnectClaudePage,
  setup: SetupPage,
  notes: NotesPage,
  references: ReferencesPage,
  graph: GraphPage,
}
loadPagesWith((route) => pageCode[route.name].preload())

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
