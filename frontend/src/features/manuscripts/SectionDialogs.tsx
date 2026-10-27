import { useState } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

type Common = { open: boolean; onOpenChange: (open: boolean) => void; busy: boolean; error: string | null }

/** Asks for a section title (new section, or rename). */
export function SectionTitleDialog({ heading, hint, initial, action, onSubmit, ...c }: Common & {
  heading: string; hint: string; initial: string; action: string; onSubmit: (title: string) => void
}) {
  const [title, setTitle] = useState(initial)
  return (
    <Dialog open={c.open} onOpenChange={c.onOpenChange}>
      <DialogContent>
        <form onSubmit={(e) => { e.preventDefault(); onSubmit(title.trim()) }} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{heading}</DialogTitle>
            <DialogDescription>{hint}</DialogDescription>
          </DialogHeader>
          <Input aria-label="Section title" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus placeholder="Related work" />
          {c.error && <Alert variant="destructive"><AlertDescription>{c.error}</AlertDescription></Alert>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => c.onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={c.busy || !title.trim()}>{action}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Names the file that goes, and says History can bring it back. */
export function DeleteSectionDialog({ path, onConfirm, ...c }: Common & { path: string; onConfirm: () => void }) {
  return (
    <Dialog open={c.open} onOpenChange={c.onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete {path}?</DialogTitle>
          <DialogDescription>The file and its \input line in the main file go. History can bring them back.</DialogDescription>
        </DialogHeader>
        {c.error && <Alert variant="destructive"><AlertDescription>{c.error}</AlertDescription></Alert>}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => c.onOpenChange(false)}>Cancel</Button>
          <Button type="button" variant="destructive" disabled={c.busy} onClick={onConfirm}>Delete</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
