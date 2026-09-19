import { useState } from 'react'
import { useFinishSetup } from '@/api/queries'
import { fadeIn } from '@/components/motion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { SetupChat } from './SetupChat'
import { SetupSearch } from './SetupSearch'
import { SKIPPED, type SetupStep } from './setup'

const STEPS: { step: SetupStep; label: string }[] = [
  { step: 'chat', label: '1. Chat' },
  { step: 'search', label: '2. Search' },
]

/**
 * `#/setup` (spec §5): a chat model, then a search source, each downloaded only if picked, with Skip on each step and
 * here. Finish and Skip mark setup done on the server, so no browser and no app window opens it again.
 */
export function SetupPage() {
  const [step, setStep] = useState<SetupStep>('chat')
  const finish = useFinishSetup()

  function done() {
    finish.mutate(undefined, {
      onSuccess: () => {
        window.location.hash = '#/'
      },
    })
  }

  return (
    <main className={cn('mx-auto flex max-w-3xl flex-col gap-8 px-4 py-6', fadeIn)}>
      <div className="flex flex-col gap-2">
        <h1 className="font-heading text-3xl font-semibold">Set up PaperLab</h1>
        <p className="text-sm text-muted-foreground">Choose the models PaperLab uses. Nothing downloads until you pick it.</p>
        <ol aria-label="Setup steps" className="flex gap-4 text-sm text-muted-foreground">
          {STEPS.map((each) => (
            <li
              key={each.step}
              aria-current={each.step === step ? 'step' : undefined}
              className={cn(each.step === step && 'font-medium text-foreground')}
            >
              {each.label}
            </li>
          ))}
        </ol>
      </div>

      {step === 'chat' ? <SetupChat onNext={() => setStep('search')} /> : <SetupSearch onFinish={done} />}

      {finish.error && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{finish.error.message}</AlertDescription>
        </Alert>
      )}
      <div className="flex flex-wrap items-center gap-3 border-t border-glass-border pt-4">
        <Button variant="ghost" disabled={finish.isPending} onClick={done}>
          Skip setup
        </Button>
        <p className="text-sm text-muted-foreground">{SKIPPED}</p>
      </div>
    </main>
  )
}
