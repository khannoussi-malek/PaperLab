import { Mic } from 'lucide-react'
import { useVoiceStatus } from '@/api/queries'
import type { VoiceStatus } from '@/api/client'
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

/** Why the button can't be used yet, per stage. A failed status read says so instead of "getting ready" forever. */
function notReadyTooltip(status: VoiceStatus | undefined, statusFailed: boolean): string | undefined {
  if (status?.stage === 'ready') return undefined
  if (statusFailed) return 'Voice status unavailable. Try again in a moment.'
  if (status?.stage === 'off') return "Voice isn't running. Turn it on in Settings → Voice."
  if (status?.stage === 'failed') return status.detail || 'Voice failed to start.'
  return 'Voice is getting ready'
}

type Props = {
  voice: ReturnType<typeof useVoiceTurn>
  /** Typed chat is busy: the microphone can't be turned on now, but an open one can always be turned off. */
  disabled?: boolean
}

/** The microphone toggle for the question box. While it is on, "Listening" stays visible so the reader knows.
 * It can only be turned on once the voice program is ready; an open microphone can always be turned off. */
export function VoiceButton({ voice, disabled }: Props) {
  const statusQuery = useVoiceStatus()
  const tooltip = notReadyTooltip(statusQuery.data, statusQuery.isError)
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
        title={voice.on ? undefined : tooltip}
        className={cn(pressable)}
        disabled={!voice.on && (disabled === true || tooltip !== undefined)}
        onClick={() => (voice.on ? voice.stop() : void voice.start())}
      >
        <Mic aria-hidden />
      </Button>
    </>
  )
}
