import type { PanelLimits } from '@/components/panelWidth'

/** The editor's PDF column. Up to 60% of the window, so the source always keeps the larger part. */
export const MANUSCRIPT_PDF: PanelLimits = {
  storageKey: 'paperlab-manuscript-pdf-width',
  defaultWidth: 520,
  minWidth: 360,
  maxShare: 0.6,
}
