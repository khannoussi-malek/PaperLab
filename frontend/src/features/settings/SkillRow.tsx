import { Copy, Eye, EyeOff, Pencil, RotateCcw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { Skill } from '@/api/client'
import { useCreateSkill, useResetSkill, useSetSkillDefault, useUpdateSkill } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { DeleteSkillDialog } from './DeleteSkillDialog'
import { SkillEditorDialog } from './SkillEditorDialog'
import { allowsDefault, duplicateLabel, SCOPE_LABELS, skillErrorMessage, STATE_LABELS } from './skillRules'

type Props = { skill: Skill; /** Every label in use, so a duplicate gets a free one. */ labels: readonly string[] }

/** One skill in Settings: its badges and every action the scope and state allow. */
export function SkillRow({ skill, labels }: Props) {
  const create = useCreateSkill()
  const update = useUpdateSkill()
  const reset = useResetSkill()
  const setDefault = useSetSkillDefault()
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Every action on the row reports into one status line, so starting one clears the others' stale errors.
  const actions = [create, update, reset, setDefault]
  const actionError = actions.map((action) => action.error).find((error) => error !== null) ?? null
  function start(run: () => void) {
    for (const action of actions) action.reset()
    run()
  }

  function duplicate() {
    start(() =>
      create.mutate({
        label: duplicateLabel(skill.label, labels),
        description: skill.description,
        scope: skill.scope,
        instructions: skill.instructions,
        lens: skill.lens,
      }),
    )
  }

  return (
    <article
      className={cn(glass, 'ring-1 ring-glass-border rounded-xl p-4 flex flex-col gap-3', !skill.is_listed && 'opacity-60')}
      data-skill-id={skill.id}
    >
      <div className="min-w-0">
        <h3 className="truncate font-heading text-lg font-semibold" title={skill.label}>
          {skill.label}
        </h3>
        {skill.description && <p className="text-sm text-muted-foreground">{skill.description}</p>}
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <Badge variant="outline">{SCOPE_LABELS[skill.scope]}</Badge>
          <Badge variant="secondary">{STATE_LABELS[skill.state]}</Badge>
          {skill.is_paper_default && <Badge>Paper default</Badge>}
          {skill.is_workspace_default && <Badge>Workspace default</Badge>}
          {!skill.is_listed && <Badge variant="outline">Hidden</Badge>}
        </div>
      </div>

      {actionError && (
        <Alert variant="destructive">
          <AlertDescription>{skillErrorMessage(actionError)}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap gap-1.5 border-t border-glass-border pt-3">
        <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
          <Pencil aria-hidden />
          Edit
        </Button>
        <Button variant="ghost" size="sm" onClick={duplicate} disabled={create.isPending}>
          <Copy aria-hidden />
          Duplicate
        </Button>
        {allowsDefault(skill.scope, 'paper') && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => start(() => setDefault.mutate({ id: skill.id, scope: 'paper', on: !skill.is_paper_default }))}
          >
            {skill.is_paper_default ? 'Remove paper default' : 'Set as paper default'}
          </Button>
        )}
        {allowsDefault(skill.scope, 'workspace') && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => start(() => setDefault.mutate({ id: skill.id, scope: 'workspace', on: !skill.is_workspace_default }))}
          >
            {skill.is_workspace_default ? 'Remove workspace default' : 'Set as workspace default'}
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={() => start(() => update.mutate({ id: skill.id, is_listed: !skill.is_listed }))}>
          {skill.is_listed ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
          {skill.is_listed ? 'Hide' : 'Show'}
        </Button>
        {skill.state === 'edited' && (
          <Button variant="ghost" size="sm" onClick={() => start(() => reset.mutate(skill.id))}>
            <RotateCcw aria-hidden />
            Reset
          </Button>
        )}
        {skill.state === 'custom' && (
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            onClick={() => setDeleting(true)}
          >
            <Trash2 aria-hidden />
            Delete
          </Button>
        )}
      </div>

      {editing && <SkillEditorDialog open onOpenChange={setEditing} skill={skill} />}
      {deleting && <DeleteSkillDialog skill={skill} onClose={() => setDeleting(false)} />}
    </article>
  )
}
