import { EllipsisVertical, Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { Workspace } from '@/api/client'
import { useWorkspaceMutations, useWorkspaces } from '@/api/queries'
import { glass } from '@/components/glass'
import { railItem } from '@/components/nav'
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

type NameFormProps = {
  initial?: string
  error: string | null
  /** True while a create/rename request is in flight: a second Enter must not send a second one. */
  pending: boolean
  onSubmit: (name: string) => void
  /** `'escape'`: the field should hand focus to whatever it replaced. `'blank'`: focus already left on its own. */
  onCancel: (reason: 'escape' | 'blank') => void
  /** Called on every keystroke, so an error about the previous name goes away. */
  onEdit: () => void
}

/** An inline name field. Enter saves, Escape cancels, and leaving it while blank cancels. */
function NameForm({ initial = '', error, pending, onSubmit, onCancel, onEdit }: NameFormProps) {
  const [name, setName] = useState(initial)
  const [blank, setBlank] = useState(false)
  // `pending` only reflects the mutation's own state once React re-renders with it; a second Enter can
  // fire before that happens. This ref closes that window: set synchronously, cleared once `pending` settles.
  const submittingRef = useRef(false)
  useEffect(() => {
    if (!pending) submittingRef.current = false
  }, [pending])
  const shown = blank ? 'Enter a name' : error
  return (
    <form
      className="flex flex-1 flex-col gap-1"
      onSubmit={(e) => {
        e.preventDefault()
        if (pending || submittingRef.current) return
        if (name.trim()) {
          submittingRef.current = true
          onSubmit(name.trim())
        } else setBlank(true)
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
        onKeyDown={(e) => e.key === 'Escape' && onCancel('escape')}
        onBlur={() => !name.trim() && onCancel('blank')}
      />
      {shown && (
        <p role="alert" className="px-1 text-xs text-destructive">
          {shown}
        </p>
      )}
    </form>
  )
}

/** The workspaces section of the navigation rail: every workspace, alphabetically, with its own row menu. */
export function WorkspaceSidebar({ activeId }: { activeId: string | null }) {
  const workspaces = useWorkspaces()
  const { create, rename, remove } = useWorkspaceMutations()
  const [creating, setCreating] = useState(false)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  // The API already orders workspaces by name (Postgres collation); no client re-sort.
  const sorted = workspaces.data ?? []

  const newWorkspaceButtonRef = useRef<HTMLButtonElement>(null)
  const triggerRefs = useRef(new Map<string, HTMLButtonElement>())
  // Set right before closing a field for a reason that should move focus, once the DOM has somewhere to put it.
  const focusNewButtonRef = useRef(false)
  const focusTriggerIdRef = useRef<string | null>(null)
  // Set only while opening Rename: its trigger disappears in this same render, so Radix's own
  // "hand focus back to the trigger" on close would find nothing there.
  const suppressMenuAutoFocusRef = useRef(false)

  // Runs after the "New workspace" button is back in the DOM, once `creating` flips to false.
  useEffect(() => {
    if (!creating && focusNewButtonRef.current) {
      focusNewButtonRef.current = false
      newWorkspaceButtonRef.current?.focus()
    }
  }, [creating])

  // Runs after a row's trigger is back in the DOM, once `renamingId` flips off it.
  useEffect(() => {
    if (renamingId === null && focusTriggerIdRef.current) {
      triggerRefs.current.get(focusTriggerIdRef.current)?.focus()
      focusTriggerIdRef.current = null
    }
  }, [renamingId])

  function startCreating() {
    create.reset()
    setCreating(true)
  }

  function cancelCreating(refocus: boolean) {
    if (refocus) focusNewButtonRef.current = true
    setCreating(false)
  }

  function startRenaming(workspace: Workspace) {
    rename.reset()
    suppressMenuAutoFocusRef.current = true
    setRenamingId(workspace.id)
  }

  function cancelRenaming(workspaceId: string, refocus: boolean) {
    if (refocus) focusTriggerIdRef.current = workspaceId
    setRenamingId(null)
  }

  function createWorkspace(name: string) {
    create.mutate(name, {
      onSuccess: (workspace) => {
        cancelCreating(true)
        window.location.hash = workspaceHref(workspace.id)
      },
    })
  }

  function renameWorkspace(workspace: Workspace, name: string) {
    if (name === workspace.name) return cancelRenaming(workspace.id, true)
    rename.mutate({ id: workspace.id, name }, { onSuccess: () => cancelRenaming(workspace.id, true) })
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
    // Nested inside the rail's own `nav`: this one keeps its name, so "the workspaces" stays a region of its own.
    <nav aria-label="Workspaces" className="flex flex-col gap-0.5">
      <h2 className="px-2 pt-1 pb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">Workspaces</h2>
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
                pending={rename.isPending}
                onSubmit={(name) => renameWorkspace(workspace, name)}
                onCancel={(reason) => cancelRenaming(workspace.id, reason === 'escape')}
                onEdit={rename.reset}
              />
            ) : (
              <>
                <a
                  href={workspaceHref(workspace.id)}
                  title={workspace.name}
                  aria-current={workspace.id === activeId ? 'page' : undefined}
                  className={railItem(workspace.id === activeId)}
                >
                  <span className="truncate">{workspace.name}</span>
                </a>
                {/* modal={false}: Radix's default modal DropdownMenu keeps the rest of the page aria-hidden
                    until its exit animation finishes closing it, which can outlast a fast interaction. */}
                <DropdownMenu modal={false}>
                  <DropdownMenuTrigger asChild>
                    <Button
                      ref={(el) => {
                        if (el) triggerRefs.current.set(workspace.id, el)
                        else triggerRefs.current.delete(workspace.id)
                      }}
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
                    // Only Rename's trigger disappears on close; every other close can take Radix's default
                    // (hand focus back to the trigger), including Escape and Delete's own confirm-then-mutate.
                    onCloseAutoFocus={(event) => {
                      if (!suppressMenuAutoFocusRef.current) return
                      event.preventDefault()
                      suppressMenuAutoFocusRef.current = false
                    }}
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
          pending={create.isPending}
          onSubmit={createWorkspace}
          onCancel={(reason) => cancelCreating(reason === 'escape')}
          onEdit={create.reset}
        />
      ) : (
        <Button
          ref={newWorkspaceButtonRef}
          variant="ghost"
          size="sm"
          className="justify-start text-muted-foreground"
          onClick={startCreating}
        >
          <Plus aria-hidden />
          New workspace
        </Button>
      )}
    </nav>
  )
}
