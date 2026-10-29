import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { PILES, PILE_ORDER } from './piles'

const ARROW: Record<string, string> = { ArrowRight: '→', ArrowDown: '↓', ArrowUp: '↑', ArrowLeft: '←', ' ': 'Space' }

const ROWS: [string, string][] = [
  ...PILE_ORDER.map((p): [string, string] => [`${ARROW[PILES[p].arrow]} or ${PILES[p].key}`, PILES[p].label]),
  ['U or Ctrl/⌘ Z', 'Undo the last decision'],
  ['P', 'Show or hide the PDF'],
  ['A', 'Focus the abstract'],
  ['F6 / Shift F6', 'Move between the card, the PDF and the controls'],
  ['?', 'This list'],
  ['Esc', 'Cancel a reason, close this list, then leave the desk'],
]

/** Only the keys that exist. */
export function ShortcutHelp({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Keyboard shortcuts</DialogTitle>
        <DialogDescription>Not relevant asks for a reason first: then 1 to 6 pick it.</DialogDescription>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          {ROWS.map(([k, what]) => (
            <div key={k} className="contents">
              <dt><kbd className="rounded border border-border px-1">{k}</kbd></dt>
              <dd>{what}</dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  )
}
