import { useSnowball } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { workspaceHref } from '@/lib/route'
import { snowballMessage } from './ScreeningTab'
import { friendlySnowballError } from './snowballText'

/** The visible way to start a snowball from one hit, and to walk the tree from it. */
export function HitSnowball({ workspaceId, hitId }: { workspaceId: string; hitId: string }) {
  const snowball = useSnowball(workspaceId)
  const run = () => snowball.mutate({ seed_hit_ids: [hitId], seed_paper_ids: [], backward: true, forward: true })
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" size="sm" variant="outline" disabled={snowball.isPending} onClick={run}>
          {snowball.isPending ? 'Snowballing…' : 'Find citing & cited papers'}
        </Button>
        <a href={`${workspaceHref(workspaceId, 'tree')}&navPaper=${hitId}`} className="text-xs text-primary hover:underline">
          Navigate from here
        </a>
      </div>
      {snowball.data && <p className="text-xs text-muted-foreground">{snowballMessage(snowball.data)}</p>}
      {snowball.isError && <p role="alert" className="text-xs text-destructive">{friendlySnowballError(snowball.error.message)}</p>}
    </div>
  )
}
