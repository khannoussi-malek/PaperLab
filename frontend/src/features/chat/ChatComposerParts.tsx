import { ChartColumn, CornerDownRight, Files, Settings2, X } from 'lucide-react'
import type { ComponentProps, Dispatch, SetStateAction } from 'react'
import type { ChatScope } from '@/entities'
import { Button } from '@/components/ui/button'
import { pressable } from '@/components/motion'
import { settingsHref } from '@/router/route'
import { cn } from '@/lib/utils'
import { ModelPicker } from './ModelPicker'
import { SkillPicker } from './SkillPicker'

/** The chip above the question box naming the saved answer the next question follows up. */
export function FollowingChip({ question, onStop }: { question: string; onStop: () => void }) {
  return (
    <p className="chat-following flex min-w-0 items-center gap-1.5 px-1 text-xs text-muted-foreground">
      <CornerDownRight aria-hidden className="size-3.5 shrink-0" />
      <span className="min-w-0 truncate" title={question}>
        Following: {question}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="icon-xs"
        className={cn('ml-auto', pressable)}
        aria-label="Stop following"
        onClick={onStop}
      >
        <X aria-hidden />
      </Button>
    </p>
  )
}

/** The row of model, skill and mode toggles under the question box. */
export function ComposerOptions({
  kind,
  models,
  modelId,
  onPickModel,
  skills,
  skillId,
  onSkillPick,
  eachPaper,
  setEachPaper,
  chartMode,
  setChartMode,
}: {
  kind: ChatScope['kind']
  models: ComponentProps<typeof ModelPicker>['models']
  modelId: ComponentProps<typeof ModelPicker>['value']
  onPickModel: ComponentProps<typeof ModelPicker>['onChange']
  skills: ComponentProps<typeof SkillPicker>['skills'] | undefined
  skillId: ComponentProps<typeof SkillPicker>['value']
  onSkillPick: ComponentProps<typeof SkillPicker>['onChange']
  eachPaper: boolean
  setEachPaper: Dispatch<SetStateAction<boolean>>
  chartMode: boolean
  setChartMode: Dispatch<SetStateAction<boolean>>
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <ModelPicker models={models} value={modelId} onChange={onPickModel} />
      {kind !== 'hit' && skills && <SkillPicker skills={skills} value={skillId} onChange={onSkillPick} />}
      {kind === 'workspace' && (
        <Button
          type="button"
          size="sm"
          variant={eachPaper ? 'secondary' : 'ghost'}
          aria-pressed={eachPaper}
          title="Asks the model once per paper, up to 10, then answers from what each says"
          onClick={() => setEachPaper((on) => !on)}
        >
          <Files aria-hidden />
          Ask each paper
        </Button>
      )}
      {kind !== 'hit' && (
        <Button
          type="button"
          size="sm"
          variant={chartMode ? 'secondary' : 'ghost'}
          aria-pressed={chartMode}
          title="Draw a chart from this chat's captured tables instead of writing an answer"
          onClick={() => setChartMode((on) => !on)}
        >
          <ChartColumn aria-hidden />
          Chart
        </Button>
      )}
    </div>
  )
}

/** Errors and hints under the composer: chart and voice problems, model loading, and the set-up link. */
export function ComposerAlerts({
  kind,
  chartError,
  voiceProblem,
  modelsError,
  noModels,
  unavailable,
}: {
  kind: ChatScope['kind']
  chartError: { message: string } | null
  voiceProblem: string | null | undefined
  modelsError: boolean
  noModels: boolean
  unavailable?: string
}) {
  return (
    <>
      {chartError && (
        <p role="alert" className="px-1 text-xs text-destructive">
          {chartError.message === 'no_datasets'
            ? `No captured tables in this ${kind} yet. Capture one in a paper's Data tab first.`
            : chartError.message}
        </p>
      )}
      {voiceProblem && (
        <p role="alert" className="px-1 text-xs text-destructive">
          {voiceProblem}
        </p>
      )}
      {modelsError && <p className="px-1 text-xs text-muted-foreground">Couldn’t load your models; using the default.</p>}
      {noModels && (
        <a href={settingsHref} className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors duration-150 hover:text-foreground">
          <Settings2 aria-hidden className="size-3.5" />
          Set up a model
        </a>
      )}
      <p id="chat-question-hint" className="px-1 text-xs text-muted-foreground">
        {unavailable ?? (noModels ? 'Set up a model to chat.' : 'Enter to send · Shift+Enter for a new line')}
      </p>
    </>
  )
}
