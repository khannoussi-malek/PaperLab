import { Bot, BookOpen, MonitorCog, Plug, Search, type LucideIcon } from 'lucide-react'
import { AppShell } from '@/components/AppShell'
import { railItem } from '@/components/nav'
import { Button } from '@/components/ui/button'
import { connectClaudeHref, settingsSectionHref, useRoute, type SettingsSection } from '@/lib/route'
import { DesktopSettings } from './DesktopSettings'
import { EmbeddingSettings } from './EmbeddingSettings'
import { useDesktop } from './desktop'
import { ModelsSettings } from './ModelsSettings'
import { PaperSourcesSettings } from './PaperSourcesSettings'

type Section = { id: SettingsSection; label: string; icon: LucideIcon }

const SECTIONS: Section[] = [
  { id: 'models', label: 'Model connections', icon: Bot },
  { id: 'sources', label: 'Paper sources', icon: BookOpen },
  { id: 'search', label: 'Search', icon: Search },
  { id: 'desktop', label: 'Desktop app', icon: MonitorCog },
  { id: 'claude', label: 'Connect Claude', icon: Plug },
]

function ConnectClaudeSection() {
  return (
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
  )
}

/** `#/settings/<section>`: one section at a time, chosen from the list beside it, as a desktop app's settings do. */
export function SettingsPage() {
  const route = useRoute()
  const desktop = useDesktop()
  // The desktop section exists only inside the app, so it is not offered in a browser either.
  const sections = SECTIONS.filter((section) => section.id !== 'desktop' || desktop !== null)
  const asked = route.name === 'settings' ? route.section : 'models'
  const current = sections.some((section) => section.id === asked) ? asked : 'models'

  return (
    <AppShell title="Settings">
      <div className="flex flex-col gap-6 sm:flex-row sm:gap-8">
        <nav aria-label="Settings sections" className="shrink-0 self-start sm:sticky sm:top-6 sm:w-56">
          <ul className="flex flex-col gap-1">
            {sections.map(({ id, label, icon: Icon }) => (
              <li key={id}>
                <a
                  href={settingsSectionHref(id)}
                  aria-current={id === current ? 'page' : undefined}
                  className={railItem(id === current)}
                >
                  <Icon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
                  <span className="truncate">{label}</span>
                </a>
              </li>
            ))}
          </ul>
        </nav>
        {/* Settings is prose and forms: a reading-width column, as macOS System Settings and Zotero's own do. */}
        <div className="flex max-w-3xl flex-1 flex-col gap-8">
          {current === 'models' && <ModelsSettings />}
          {current === 'sources' && <PaperSourcesSettings />}
          {current === 'search' && <EmbeddingSettings />}
          {current === 'desktop' && <DesktopSettings />}
          {current === 'claude' && <ConnectClaudeSection />}
        </div>
      </div>
    </AppShell>
  )
}
