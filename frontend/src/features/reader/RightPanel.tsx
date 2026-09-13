import type { ReactNode } from 'react'
import { glass } from '@/components/glass'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { ReaderTab } from '@/lib/route'
import { cn } from '@/lib/utils'

type Props = {
  tab: ReaderTab
  onTabChange: (tab: ReaderTab) => void
  notes: ReactNode
  chat: ReactNode
}

// Both panels stay mounted, so a streaming answer, a note draft and each panel's scroll position survive a
// tab switch. `text-base` undoes TabsContent's `text-sm`, which would shrink the note cards.
const panel = 'flex min-h-0 flex-1 flex-col text-base data-[state=inactive]:hidden'

export function RightPanel({ tab, onTabChange, notes, chat }: Props) {
  return (
    <Tabs
      value={tab}
      onValueChange={(value) => onTabChange(value as ReaderTab)}
      className={cn('min-h-0 gap-0 border-l border-glass-border', glass)}
    >
      <TabsList className="mx-4 mt-3 w-auto">
        <TabsTrigger value="notes">Notes</TabsTrigger>
        <TabsTrigger value="chat">Chat</TabsTrigger>
      </TabsList>
      <TabsContent value="notes" forceMount className={panel}>
        {notes}
      </TabsContent>
      <TabsContent value="chat" forceMount className={panel}>
        {chat}
      </TabsContent>
    </Tabs>
  )
}
