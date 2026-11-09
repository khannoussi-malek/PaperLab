import { useState } from 'react'
import { sileo } from 'sileo'
import type { ChatScope, ProvNode } from '@/api/client'
import { useSearchHit, useWorkspacePapers } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { ChatPanel } from '@/features/chat/ChatPanel'
import { chunkHref, noteHref, readerHref } from '@/lib/route'

const NARROW = '(max-width: 900px)'
const startsFolded = () => typeof window.matchMedia === 'function' && window.matchMedia(NARROW).matches

/** "Ask the AI" about the paper the owner is standing on, docked on the right (a drawer below 900px). A library paper
 * uses its paper chat; a hit uses the hit chat, which reads the abstract until the paper has a file. */
export function AskPanel({ workspaceId, node }: { workspaceId: string; node: ProvNode }) {
  const [folded, setFolded] = useState(startsFolded)
  const isLibrary = node.id.startsWith('paper:')
  const libraryId = isLibrary ? (node.paper_id ?? node.id.slice(6)) : null
  const hit = useSearchHit(workspaceId, isLibrary ? null : node.id).data
  const library = useWorkspacePapers(workspaceId).data
  const scope: ChatScope = libraryId ? { kind: 'paper', id: libraryId } : { kind: 'hit', workspaceId, id: node.id }
  const hasFile = libraryId
    ? library?.find((p) => p.id === libraryId)?.has_pdf === true
    : !!hit?.paper_id && (hit.acquisition_status === 'imported' || hit.acquisition_status === 'manual')

  if (folded) {
    return (
      <Button type="button" size="sm" variant="outline" className="self-start max-[900px]:fixed max-[900px]:right-3 max-[900px]:bottom-3 max-[900px]:z-40" onClick={() => setFolded(false)}>
        Ask the AI
      </Button>
    )
  }
  return (
    <aside
      aria-label="Ask the AI"
      className="flex w-[340px] shrink-0 flex-col overflow-hidden rounded-lg border border-border bg-card max-[900px]:fixed max-[900px]:inset-y-0 max-[900px]:right-0 max-[900px]:z-40 max-[900px]:max-w-full max-[900px]:shadow-xl"
    >
      <div className="flex items-start gap-2 border-b border-border px-3 py-2">
        <div className="min-w-0 flex-1">
          <h2 className="font-heading text-base">Ask the AI</h2>
          <p className="text-xs text-muted-foreground">{`Reads: ${hasFile ? 'full text' : 'abstract only'}`}</p>
        </div>
        <Button type="button" size="icon-xs" variant="ghost" aria-label="Fold Ask the AI" onClick={() => setFolded(true)}>⟩</Button>
      </div>
      <ChatPanel
        key={`${scope.kind}:${scope.id}`}
        scope={scope}
        onCite={(source) => {
          window.location.hash = 'note_id' in source ? noteHref(source.paper_id, source.note_id) : source.from_abstract ? readerHref(source.paper_id) : chunkHref(source.paper_id, source.chunk_id, source.page)
        }}
        onPromoted={() => sileo.success({ title: 'Saved as a note' })}
      />
    </aside>
  )
}
