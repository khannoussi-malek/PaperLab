import { useEffect, useRef, type ReactNode } from 'react'
import { glass } from '@/components/glass'
import { fadeIn } from '@/components/motion'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { ReaderTab } from '@/lib/route'
import { cn } from '@/lib/utils'
import { PanelResizeHandle } from '@/components/PanelResizeHandle'
import { READER_PANEL } from './panelWidth'

type Props = {
  tab: ReaderTab
  onTabChange: (tab: ReaderTab) => void
  width: number
  onWidthChange: (width: number) => void
  notes: ReactNode
  chat: ReactNode
  data: ReactNode
  similar: ReactNode
  references: ReactNode
  evidence: ReactNode
  lens: ReactNode
}

// Both panels stay mounted, so a streaming answer, a note draft and each panel's scroll position survive a
// tab switch. `text-base` undoes TabsContent's `text-sm`, which would shrink the note cards.
const panel = cn('flex min-h-0 flex-1 flex-col text-base data-[state=inactive]:hidden', fadeIn)

export function RightPanel({ tab, onTabChange, width, onWidthChange, notes, chat, data, similar, references, evidence, lens }: Props) {
  const listRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    // The active tab stays in view when the list scrolls (seven tabs at the 320 px minimum).
    listRef.current?.querySelector('[data-state="active"]')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  }, [tab])
  return (
    <Tabs
      value={tab}
      onValueChange={(value) => onTabChange(value as ReaderTab)}
      className={cn('reader-panel relative min-h-0 gap-0 border-l border-glass-border', glass)}
    >
      <PanelResizeHandle limits={READER_PANEL} width={width} onWidthChange={onWidthChange} />
      <TabsList ref={listRef} id="reader-panel-tabs" className="mx-4 mt-3 max-w-full justify-start overflow-x-auto">
        <TabsTrigger value="notes">Notes</TabsTrigger>
        <TabsTrigger value="chat">Chat</TabsTrigger>
        <TabsTrigger value="data">Data</TabsTrigger>
        <TabsTrigger value="similar">Similar</TabsTrigger>
        <TabsTrigger value="references">References</TabsTrigger>
        <TabsTrigger value="evidence">Evidence</TabsTrigger>
        <TabsTrigger value="lens">Lens</TabsTrigger>
      </TabsList>
      <TabsContent value="notes" forceMount className={panel}>
        {notes}
      </TabsContent>
      <TabsContent value="chat" forceMount className={panel}>
        {chat}
      </TabsContent>
      <TabsContent value="data" forceMount className={panel}>
        {data}
      </TabsContent>
      <TabsContent value="similar" forceMount className={panel}>
        {similar}
      </TabsContent>
      <TabsContent value="references" forceMount className={panel}>
        {references}
      </TabsContent>
      <TabsContent value="evidence" forceMount className={panel}>
        {evidence}
      </TabsContent>
      <TabsContent value="lens" forceMount className={panel}>
        {lens}
      </TabsContent>
    </Tabs>
  )
}
