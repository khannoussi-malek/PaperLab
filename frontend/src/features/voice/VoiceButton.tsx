import { Mic } from 'lucide-react'
import { pressable } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { useVoiceTurn, VoiceState } from './useVoiceTurn'

const LABEL: Record<VoiceState, string> = {
  off: 'Ask out loud',
  starting: 'Starting the microphone',
  listening: 'Listening, press to turn off',
  thinking: 'Thinking, press to turn off',
  speaking: 'Speaking, press to turn off',
}

type Props = {
  voice: ReturnType<typeof useVoiceTurn>
  /** Typed chat is busy: the microphone can't be turned on now, but an open one can always be turned off. */
  disabled?: boolean
}

/** The microphone toggle for the question box. While it is on, "Listening" stays visible so the reader knows. */
export function VoiceButton({ voice, disabled }: Props) {
  return (
    <>
      {voice.on && (
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-destructive" />
          {voice.state === 'starting' ? 'Starting' : 'Listening'}
        </span>
      )}
      <Button
        type="button"
        size="icon-sm"
        variant={voice.on ? 'secondary' : 'ghost'}
        aria-pressed={voice.on}
        aria-label={LABEL[voice.state]}
        className={cn(pressable)}
        disabled={disabled && !voice.on}
        onClick={() => (voice.on ? voice.stop() : void voice.start())}
      >
        <Mic aria-hidden />
      </Button>
    </>
  )
}
