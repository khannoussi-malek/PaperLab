import { useState } from 'react'
import { useCreateManuscript, useManuscriptTemplates } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { manuscriptHref } from '@/lib/route'
import { manuscriptFailure } from './errors'

type Props = { workspaceId: string | null; open: boolean; onOpenChange: (open: boolean) => void }

/** Title plus a template; creating opens the new manuscript's editor. */
export function NewManuscriptDialog({ workspaceId, open, onOpenChange }: Props) {
  const templates = useManuscriptTemplates()
  const create = useCreateManuscript()
  const [title, setTitle] = useState('')
  const [picked, setPicked] = useState<string | null>(null)
  const template = picked ?? templates.data?.[0]?.name ?? ''

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    create.mutate(
      { title: title.trim(), template, workspace_id: workspaceId },
      { onSuccess: (created) => window.location.assign(manuscriptHref(created.id)) },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>New manuscript</DialogTitle>
            <DialogDescription>Give it a title and pick a LaTeX template to start from.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="manuscript-title">Title</Label>
            <Input id="manuscript-title" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
          </div>
          <RadioGroup value={template} onValueChange={setPicked} aria-label="Template" className="gap-2">
            {templates.data?.map((t) => (
              <div key={t.name} className="flex items-center gap-2">
                <RadioGroupItem value={t.name} id={`template-${t.name}`} />
                <Label htmlFor={`template-${t.name}`}>{t.label}</Label>
              </div>
            ))}
          </RadioGroup>
          {(templates.error ?? create.error) && (
            <Alert variant="destructive">
              <AlertDescription>{manuscriptFailure((templates.error ?? create.error)!)}</AlertDescription>
            </Alert>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={!title.trim() || !template || create.isPending}>
              {create.isPending ? 'Creating…' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
