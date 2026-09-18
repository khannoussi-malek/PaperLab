import { ChartBuilderPage } from './features/charts/ChartBuilderPage'
import { ChartPage } from './features/charts/ChartPage'
import { ChartsPage } from './features/charts/ChartsPage'
import { ConnectClaudePage } from './features/connect-claude/ConnectClaudePage'
import { DatasetPage } from './features/data/DatasetPage'
import { GraphPage } from './features/graph/GraphPage'
import { LibraryPage } from './features/library/LibraryPage'
import { ReaderPage } from './features/reader/ReaderPage'
import { SettingsPage } from './features/settings/SettingsPage'
import { WorkspacePage } from './features/workspaces/WorkspacePage'
import { useRoute } from './lib/route'

export default function App() {
  const route = useRoute()
  if (route.name === 'workspace') {
    // Keyed by workspace only: switching tabs must not remount the page.
    return <WorkspacePage key={route.workspaceId} workspaceId={route.workspaceId} tab={route.tab} />
  }
  if (route.name === 'reader') {
    // Keyed by paper only: switching tabs must not remount the reader.
    return <ReaderPage key={route.paperId} paperId={route.paperId} tab={route.tab} target={route.target} />
  }
  if (route.name === 'charts') {
    return <ChartsPage />
  }
  if (route.name === 'chart-builder') {
    return (
      <ChartBuilderPage key={route.chartId ?? `new-${route.datasetId ?? ''}`} chartId={route.chartId} datasetId={route.datasetId} />
    )
  }
  if (route.name === 'chart') {
    return <ChartPage key={route.chartId} chartId={route.chartId} />
  }
  if (route.name === 'dataset') {
    return <DatasetPage key={route.datasetId} datasetId={route.datasetId} focus={route.focus} />
  }
  if (route.name === 'settings') {
    return <SettingsPage />
  }
  if (route.name === 'connect-claude') {
    return <ConnectClaudePage />
  }
  if (route.name === 'graph') {
    return <GraphPage />
  }
  return <LibraryPage />
}
