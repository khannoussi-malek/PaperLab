import { useState, type FormEvent } from 'react'
import type { Skill } from '@/api/client'
import { useCreateSkill, useUpdateSkill } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Textarea } from '@/components/ui/textarea'
import { changedFields, createBody, draftOf, skillErrorMessage, SCOPE_LABELS, validateDraft, type Scope, type SkillDraft } from './skillRules'

const EDITOR_NOTE =
  "PaperLab already tells the model to cite its sources and answer in plain prose, so a skill needn't say how to format or cite."
const SCOPES: readonly Scope[] = ['paper', 'workspace', 'both']

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Omitted: "New skill". Set: "Edit skill", starting from its current values. */
  skill?: Skill
}

/** Creates a custom skill, or edits any skill; a save sends only the fields that changed. Errors stay in the dialog. */
export function SkillEditorDialog({ open, onOpenChange, skill }: Props) {
  const create = useCreateSkill()
  const update = useUpdateSkill()
  const [draft, setDraft] = useState<SkillDraft>(() => draftOf(skill))
  const [problem, setProblem] = useState<string | null>(null)
  const pending = create.isPending || update.isPending
  const serverError = skill ? update.error : create.error
  const message = problem ?? (serverError ? skillErrorMessage(serverError) : null)

  function save(event: FormEvent) {
    event.preventDefault()
    const invalid = validateDraft(draft)
    setProblem(invalid)
    if (invalid) return
    const close = { onSuccess: () => onOpenChange(false) }
    if (!skill) {
      create.mutate(createBody(draft), close)
      return
    }
    const changes = changedFields(skill, draft)
    if (Object.keys(changes).length === 0) onOpenChange(false)
    else update.mutate({ id: skill.id, ...changes }, close)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={save} noValidate className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{skill ? 'Edit skill' : 'New skill'}</DialogTitle>
          </DialogHeader>

          <div className="grid gap-1.5">
            <Label htmlFor="skill-label">Label</Label>
            <Input
              id="skill-label"
              value={draft.label}
              onChange={(e) => setDraft((d) => ({ ...d, label: e.target.value }))}
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="skill-description">Description</Label>
            <Input
              id="skill-description"
              value={draft.description}
              onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
            />
          </div>

          <fieldset className="grid gap-1.5">
            <legend className="text-sm font-medium">Use it for</legend>
            <RadioGroup
              value={draft.scope}
              onValueChange={(value) => setDraft((d) => ({ ...d, scope: value as Scope }))}
              className="flex flex-row flex-wrap gap-4"
            >
              {SCOPES.map((scope) => (
                <div key={scope} className="flex items-center gap-2">
                  <RadioGroupItem value={scope} id={`skill-scope-${scope}`} />
                  <Label htmlFor={`skill-scope-${scope}`}>{SCOPE_LABELS[scope]}</Label>
                </div>
              ))}
            </RadioGroup>
          </fieldset>

          <div className="grid gap-1.5">
            <Label htmlFor="skill-instructions">Instructions</Label>
            <Textarea
              id="skill-instructions"
              rows={8}
              value={draft.instructions}
              onChange={(e) => setDraft((d) => ({ ...d, instructions: e.target.value }))}
            />
            <p className="text-xs text-muted-foreground">{EDITOR_NOTE}</p>
          </div>

          {message && (
            <Alert variant="destructive">
              <AlertDescription>{message}</AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
