import { Fragment, useEffect, useRef } from 'react'
import { Badge } from '@/components/ui/badge'
import { TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { WorkspaceTab } from '@/lib/route'
import { Term } from './Term'
import { GROUP_LABELS, WORKSPACE_TABS, tabAriaLabel } from './workspaceTabs'

type Counts = Partial<Record<WorkspaceTab, number>>

/** The step line, with "PRISMA" explained wherever it appears. */
function StepLine({ text }: { text: string }) {
  const [before, ...after] = text.split('PRISMA')
  if (!after.length) return <>{text}</>
  return (
    <>
      {before}
      <Term term="prisma">PRISMA</Term>
      {after.join('PRISMA')}
    </>
  )
}

/** Two labelled groups of tabs, then one muted line saying what the active tab is for. Must sit inside <Tabs>. */
export function WorkspaceTabBar({ active, counts }: { active: WorkspaceTab; counts: Counts }) {
  const listRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    listRef.current?.querySelector('[data-state="active"]')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  }, [active])
  const current = WORKSPACE_TABS.find((tab) => tab.value === active)
  return (
    <div className="flex flex-col gap-2">
      <TabsList
        ref={listRef}
        className="h-auto min-w-0 max-w-full justify-start gap-1 overflow-x-auto max-md:[mask-image:linear-gradient(to_right,transparent,black_1rem,black_calc(100%-1rem),transparent)]"
      >
        {(['papers', 'review'] as const).map((group, index) => (
          <Fragment key={group}>
            {index > 0 && <div aria-hidden className="mx-1 w-px shrink-0 self-stretch bg-border" />}
            <span className="sr-only shrink-0 px-1.5 text-xs text-muted-foreground md:not-sr-only">{GROUP_LABELS[group]}</span>
            {WORKSPACE_TABS.filter((tab) => tab.group === group).map((meta) => {
              const count = counts[meta.value]
              return (
                <TabsTrigger key={meta.value} value={meta.value} aria-label={tabAriaLabel(meta, count)} className="min-h-11 shrink-0 md:min-h-0">
                  {meta.step ? `${meta.step} · ${meta.label}` : meta.label}
                  {count ? <Badge variant="secondary" aria-hidden>{count.toLocaleString('en')}</Badge> : null}
                </TabsTrigger>
              )
            })}
          </Fragment>
        ))}
      </TabsList>
      {current && (
        <p className="text-sm text-muted-foreground max-w-prose">
          <StepLine text={current.stepLine} />
        </p>
      )}
    </div>
  )
}
