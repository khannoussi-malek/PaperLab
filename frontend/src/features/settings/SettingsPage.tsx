import { ArrowLeft, Plug } from 'lucide-react'
import { fadeIn } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { connectClaudeHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { EmbeddingSettings } from './EmbeddingSettings'
import { ModelsSettings } from './ModelsSettings'
import { PaperSourcesSettings } from './PaperSourcesSettings'

/** `#/settings`: model connections (which models chat lists, and the default), paper sources, the embedding model, and
 * a link to Connect Claude. */
export function SettingsPage() {
  return (
    <main className={cn('mx-auto flex max-w-3xl flex-col gap-8 px-4 py-6', fadeIn)}>
      <div>
        <Button variant="ghost" size="sm" asChild className="-ml-2.5">
          <a href="#/">
            <ArrowLeft aria-hidden />
            Library
          </a>
        </Button>
        <h1 className="mt-1 font-heading text-3xl font-semibold">Settings</h1>
      </div>

      <ModelsSettings />
      <PaperSourcesSettings />
      <EmbeddingSettings />

      <section aria-labelledby="connect-claude-heading" className="flex flex-col gap-3">
        <h2 id="connect-claude-heading" className="font-heading text-xl font-semibold">
          Connect Claude
        </h2>
        <p className="text-sm text-muted-foreground">
          Let Claude Desktop, Claude Code or another MCP client search your library and save notes.
        </p>
        <div>
          <Button variant="outline" asChild>
            <a href={connectClaudeHref}>
              <Plug aria-hidden />
              Open Connect Claude
            </a>
          </Button>
        </div>
      </section>
    </main>
  )
}
