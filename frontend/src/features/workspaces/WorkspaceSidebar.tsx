import { EllipsisVertical, Library, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { Workspace } from '@/api/client'
import { useWorkspaceMutations, useWorkspaces } from '@/api/queries'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { workspaceHref } from '@/lib/route'
import { cn } from '@/lib/utils'

const MAX_NAME = 80 // the API's limit

/** A failed create or rename in words. The API's own code isn't meant for display; other failures show as sent. */
const nameError = (error: Error | null) =>
  error?.message === 'workspace_name_taken' ? 'A workspace with this name already exists' : (error?.message ?? null)

const itemClass = (active: boolean) =>
  cn(
    'flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none transition-colors duration-150 hover:bg-foreground/5 focus-visible:ring-3 focus-visible:ring-ring/50',
    active && 'bg-primary/10 font-medium shadow-[inset_3px_0_0_var(--color-primary)]',
  )

type NameFormProps = {
  initial?: string
  error: string | null
  onSubmit: (name: string) => void
  onCancel: () => void
  /** Called on every keystroke, so an error about the previous name goes away. */
  onEdit: () => void
}

/** An inline name field. Enter saves, Escape cancels, and leaving it while blank cancels. */
function NameForm({ initial = '', error, onSubmit, onCancel, onEdit }: NameFormProps) {
  const [name, setName] = useState(initial)
  const [blank, setBlank] = useState(false)
  const shown = blank ? 'Enter a name' : error
  return (
    <form
      className="flex flex-1 flex-col gap-1"
      onSubmit={(e) => {
        e.preventDefault()
        if (name.trim()) onSubmit(name.trim())
        else setBlank(true)
      }}
    >
      <Input
        autoFocus
        aria-label="Workspace name"
        aria-invalid={shown ? true : undefined}
        maxLength={MAX_NAME}
        value={name}
        onChange={(e) => {
          setName(e.target.value)
          setBlank(false)
          onEdit()
        }}
        onKeyDown={(e) => e.key === 'Escape' && onCancel()}
        onBlur={() => !name.trim() && onCancel()}
      />
      {shown && (
        <p role="alert" className="px-1 text-xs text-destructive">
          {shown}
        </p>
      )}
    </form>
  )
}

/** The library's navigation: All papers, then each workspace, alphabetically. */
export function WorkspaceSidebar({ activeId }: { activeId: string | null }) {
  const workspaces = useWorkspaces()
  const { create, rename, remove } = useWorkspaceMutations()
  const [creating, setCreating] = useState(false)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  // The API already orders workspaces by name (Postgres collation); no client re-sort.
  const sorted = workspaces.data ?? []

  function startCreating() {
    create.reset()
    setCreating(true)
  }

  function startRenaming(workspace: Workspace) {
    rename.reset()
    setRenamingId(workspace.id)
  }

  function createWorkspace(name: string) {
    create.mutate(name, {
      onSuccess: (workspace) => {
        setCreating(false)
        window.location.hash = workspaceHref(workspace.id)
      },
    })
  }

  function renameWorkspace(workspace: Workspace, name: string) {
    if (name === workspace.name) return setRenamingId(null)
    rename.mutate({ id: workspace.id, name }, { onSuccess: () => setRenamingId(null) })
  }

  function deleteWorkspace(workspace: Workspace) {
    if (!window.confirm(`Delete the workspace "${workspace.name}"? Papers and notes stay in your library.`)) return
    remove.mutate(workspace.id, {
      onSuccess: () => {
        if (workspace.id === activeId) window.location.hash = '#/'
      },
    })
  }

  const error = workspaces.error ?? remove.error
  return (
    <nav
      aria-label="Workspaces"
      className={cn('flex flex-col gap-0.5 self-start rounded-xl p-2 ring-1 ring-glass-border lg:sticky lg:top-6', glass)}
    >
      <a href="#/" aria-current={activeId === null ? 'page' : undefined} className={itemClass(activeId === null)}>
        <Library aria-hidden className="size-4 text-muted-foreground" />
        All papers
      </a>

      <h2 className="px-2 pt-3 pb-1 text-xs font-medium text-muted-foreground">Workspaces</h2>
      {error && (
        <p role="alert" className="px-2 text-xs text-destructive">
          {error.message}
        </p>
      )}
      <ul className="flex flex-col gap-0.5">
        {sorted.map((workspace) => (
          <li key={workspace.id} className="group flex items-center gap-1">
            {renamingId === workspace.id ? (
              <NameForm
                initial={workspace.name}
                error={nameError(rename.error)}
                onSubmit={(name) => renameWorkspace(workspace, name)}
                onCancel={() => setRenamingId(null)}
                onEdit={rename.reset}
              />
            ) : (
              <>
                <a
                  href={workspaceHref(workspace.id)}
                  title={workspace.name}
                  aria-current={workspace.id === activeId ? 'page' : undefined}
                  className={itemClass(workspace.id === activeId)}
                >
                  <span className="truncate">{workspace.name}</span>
                </a>
                {/* modal={false}: Radix's default modal mode aria-hides the rest of the page while open,
                    and Delete's window.confirm() blocks the thread that would clear it back off in time. */}
                <DropdownMenu modal={false}>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      aria-label="Workspace actions"
                      // Quiet until its row is in play, like the paper rows' delete icon.
                      className="text-muted-foreground opacity-0 group-focus-within:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100"
                    >
                      <EllipsisVertical aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="start"
                    className={cn(glass, 'bg-glass-strong ring-glass-border')}
                    // Rename puts a focused field where the trigger was; don't hand focus back to the removed trigger.
                    onCloseAutoFocus={(event) => event.preventDefault()}
                  >
                    <DropdownMenuItem onSelect={() => startRenaming(workspace)}>
                      <Pencil aria-hidden />
                      Rename
                    </DropdownMenuItem>
                    <DropdownMenuItem variant="destructive" onSelect={() => deleteWorkspace(workspace)}>
                      <Trash2 aria-hidden />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </>
            )}
          </li>
        ))}
      </ul>

      {creating ? (
        <NameForm
          error={nameError(create.error)}
          onSubmit={createWorkspace}
          onCancel={() => setCreating(false)}
          onEdit={create.reset}
        />
      ) : (
        <Button variant="ghost" size="sm" className="justify-start text-muted-foreground" onClick={startCreating}>
          <Plus aria-hidden />
          New workspace
        </Button>
      )}
    </nav>
  )
}
