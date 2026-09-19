import { Button } from '@/components/ui/button'

type Props = { next: 'Continue' | 'Finish'; busy: boolean; onNext: () => void }

/** A setup step's own buttons. Continue (or Finish) waits while the step's download runs; Skip moves on at once, and an
 * Ollama pull stops with its step (it resumes where it stopped next time). */
export function StepButtons({ next, busy, onNext }: Props) {
  return (
    <div className="flex items-center gap-2">
      <Button disabled={busy} onClick={onNext}>
        {next}
      </Button>
      <Button variant="ghost" onClick={onNext}>
        Skip
      </Button>
    </div>
  )
}
