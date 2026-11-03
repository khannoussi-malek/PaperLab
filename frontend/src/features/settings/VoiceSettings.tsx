import { useVoiceLatency, useVoiceStatus } from '@/api/queries'
import type { VoiceLatencyGroup, VoicePercentiles } from '@/api/client'
import { Alert, AlertDescription } from '@/components/ui/alert'

// The stages in the order a question goes through them, by the field each comes from.
const STAGES: [keyof VoiceLatencyGroup['warm'], string][] = [
  ['wait_ms', 'Waiting for silence'],
  ['stt_ms', 'Speech to text'],
  ['retrieval_ms', 'Finding passages'],
  ['embed_ms', 'Of that, embedding the question'],
  ['ttft_ms', "Model's first word"],
  ['first_chunk_ms', 'First full sentence'],
  ['tts_first_ms', 'First speech made'],
  ['output_ms', 'Output delay'],
  ['total_ms', 'Stop talking to first audio'],
  ['interrupt_stop_ms', 'Stopping when interrupted'],
]
const COLUMNS = [
  ['median', 'Median', 1],
  ['p90', '90th', 10],
  ['p95', '95th', 20],
  ['p99', '99th', 100],
] as const

function cell(p: VoicePercentiles, key: (typeof COLUMNS)[number][0], needs: number) {
  if (p.n === 0) return '—'
  const value = p[key]
  return value == null ? `needs ${needs} turns` : `${Math.round(value)} ms`
}

function StageTable({ title, stages }: { title: string; stages: VoiceLatencyGroup['warm'] }) {
  return (
    <table className="w-full text-sm tabular-nums">
      <caption className="pb-1 text-left text-xs font-medium text-muted-foreground">{title}</caption>
      <thead>
        <tr className="text-left text-xs text-muted-foreground">
          <th scope="col" className="font-medium">Stage</th>
          <th scope="col" className="font-medium">Turns</th>
          {COLUMNS.map(([, label]) => (
            <th key={label} scope="col" className="font-medium">{label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {STAGES.map(([field, label]) => (
          <tr key={field}>
            <th scope="row" className="py-0.5 pr-3 text-left font-normal">{label}</th>
            <td>{stages[field].n}</td>
            {COLUMNS.map(([key, name, needs]) => (
              <td key={name} className={stages[field].n > 0 && stages[field][key] === null ? 'text-xs text-muted-foreground' : ''}>
                {cell(stages[field], key, needs)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const hasTurns = (stages: VoiceLatencyGroup['warm']) => STAGES.some(([field]) => stages[field].n > 0)

function interruptLine(group: VoiceLatencyGroup) {
  return `${group.interrupts} interruptions, ${group.false_interrupts} probably false`
}

/** The "Voice" section: whether the voice program is ready, and how long each stage of a spoken question has taken. */
export function VoiceSettings() {
  const status = useVoiceStatus()
  const latency = useVoiceLatency()
  const groups = latency.data?.groups

  return (
    <section aria-labelledby="voice-heading" className="flex flex-col gap-4">
      <h2 id="voice-heading" className="font-heading text-xl font-semibold">
        Voice
      </h2>
      <p className="text-sm text-muted-foreground">Ask questions out loud and hear the answer. Here is how fast it has been.</p>

      {status.data && (
        <p className="text-sm font-medium">{status.data.ready ? 'The voice program is ready.' : status.data.detail}</p>
      )}
      {status.isError && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{status.error.message}</AlertDescription>
        </Alert>
      )}

      {latency.isError && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{latency.error.message}</AlertDescription>
        </Alert>
      )}
      {groups?.length === 0 && <p className="text-sm text-muted-foreground">Ask a question out loud to see numbers here.</p>}
      {groups?.map((group) => (
        <div key={group.model} className="flex flex-col gap-3">
          <h3 className="text-sm font-medium">{group.model}</h3>
          {hasTurns(group.warm) && <StageTable title="After the first question" stages={group.warm} />}
          {hasTurns(group.cold) && <StageTable title="First question after the voice program started" stages={group.cold} />}
          <p className="text-xs text-muted-foreground">{interruptLine(group)}</p>
        </div>
      ))}
      {groups && groups.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Times are from this computer. Each stage is its own median, so they won't add up to the total.
        </p>
      )}
    </section>
  )
}
