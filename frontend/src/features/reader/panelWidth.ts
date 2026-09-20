import type { PanelLimits } from '@/components/panelWidth'

/** The reader's right panel (Notes | Chat). The paper always keeps the larger part of the window. */
export const READER_PANEL: PanelLimits = {
  storageKey: 'paperlab-panel-width',
  defaultWidth: 360,
  minWidth: 320,
  maxShare: 0.6,
}
