/** What the desktop app's preload script puts on PaperLab's window (desktop/src/preload.ts). Absent in a browser. */
export type PaperlabDesktop = {
  getKeepRunning(): Promise<boolean>
  setKeepRunning(value: boolean): Promise<void>
  getUpdatesEnabled(): Promise<boolean>
  setUpdatesEnabled(value: boolean): Promise<void>
}

/** The bridge on `scope` (a page's window is its globalThis), or null in a normal browser and in Node. */
export function desktopBridge(scope: object): PaperlabDesktop | null {
  return (scope as { paperlabDesktop?: PaperlabDesktop }).paperlabDesktop ?? null
}

/** The desktop app's bridge, or null in a normal browser: it gates Settings' Desktop app section and Connect Claude's
 * line. It never changes while the page lives, so it needs no state. */
export function useDesktop(): PaperlabDesktop | null {
  return desktopBridge(globalThis)
}
