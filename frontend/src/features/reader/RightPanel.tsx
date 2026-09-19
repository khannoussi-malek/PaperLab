import type { ReactNode } from 'react'
import { glass } from '@/components/glass'
import { fadeIn } from '@/components/motion'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { ReaderTab } from '@/lib/route'
import { cn } from '@/lib/utils'
import { PanelResizeHandle } from './PanelResizeHandle'

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
}

// Both panels stay mounted, so a streaming answer, a note draft and each panel's scroll position survive a
// tab switch. `text-base` undoes TabsContent's `text-sm`, which would shrink the note cards.
const panel = cn('flex min-h-0 flex-1 flex-col text-base data-[state=inactive]:hidden', fadeIn)

export function RightPanel({ tab, onTabChange, width, onWidthChange, notes, chat, data, similar, references }: Props) {
  return (
    <Tabs
      value={tab}
      onValueChange={(value) => onTabChange(value as ReaderTab)}
      className={cn('reader-panel relative min-h-0 gap-0 border-l border-glass-border', glass)}
    >
      <PanelResizeHandle width={width} onWidthChange={onWidthChange} />
      <TabsList id="reader-panel-tabs" className="mx-4 mt-3 w-auto">
        <TabsTrigger value="notes">Notes</TabsTrigger>
        <TabsTrigger value="chat">Chat</TabsTrigger>
        <TabsTrigger value="data">Data</TabsTrigger>
        <TabsTrigger value="similar">Similar</TabsTrigger>
        <TabsTrigger value="references">References</TabsTrigger>
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
    </Tabs>
  )
}
