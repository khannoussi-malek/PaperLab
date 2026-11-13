import type { Skill } from '@/api/client'
import { useDeleteSkill } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { skillErrorMessage } from './skillRules'

/** Asks before a custom skill is deleted. Saved answers keep the skill name they ran with. */
export function DeleteSkillDialog({ skill, onClose }: { skill: Skill; onClose: () => void }) {
  const remove = useDeleteSkill()
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Delete "{skill.label}"?</DialogTitle>
          <DialogDescription>Saved answers keep the skill name they ran with. This cannot be undone.</DialogDescription>
        </DialogHeader>
        {remove.error && (
          <Alert variant="destructive">
            <AlertDescription>{skillErrorMessage(remove.error)}</AlertDescription>
          </Alert>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate(skill.id, { onSuccess: onClose })}>
            {remove.isPending ? 'Deleting…' : 'Delete'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
