import { Plus } from 'lucide-react'
import { useState } from 'react'
import { useSkills } from '@/api/queries'
import { LoadingState } from '@/components/LoadingState'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { SkillEditorDialog } from './SkillEditorDialog'
import { SkillRow } from './SkillRow'
import { mergeSkillLists } from './skillRules'

/** The "Skills" section: every skill, hidden ones included, with its actions. Built-in skills come from the server. */
export function SkillsSettings() {
  const paper = useSkills('paper', true)
  const workspace = useSkills('workspace', true)
  const [createOpen, setCreateOpen] = useState(false)
  const loaded = paper.data !== undefined && workspace.data !== undefined
  const failed = paper.error ?? workspace.error
  const skills = mergeSkillLists(paper.data, workspace.data)
  const labels = skills.map((skill) => skill.label)

  return (
    <section aria-labelledby="skills-heading" className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h2 id="skills-heading" className="font-heading text-xl font-semibold">
          Skills
        </h2>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus aria-hidden />
          New skill
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        A skill is a set of instructions for one kind of question. Pick one in the reader or in a workspace chat.
      </p>

      {!loaded ? (
        failed ? (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{failed.message}</AlertDescription>
            <AlertAction>
              <Button
                variant="outline"
                size="xs"
                onClick={() => {
                  void paper.refetch()
                  void workspace.refetch()
                }}
              >
                Retry
              </Button>
            </AlertAction>
          </Alert>
        ) : (
          <LoadingState failureCount={paper.failureCount} />
        )
      ) : (
        <div className="flex flex-col gap-3">
          {skills.map((skill) => (
            <SkillRow key={skill.id} skill={skill} labels={labels} />
          ))}
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Four skills draw on the community LLM reporting guidelines at llm-guidelines.org.
      </p>

      {createOpen && <SkillEditorDialog open onOpenChange={setCreateOpen} />}
    </section>
  )
}
