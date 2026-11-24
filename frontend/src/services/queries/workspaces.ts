import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { keys } from './core'
import { papersPollInterval } from './papers'

/** Workspaces with their paper and note counts. */
export const useWorkspaces = () => useQuery({ queryKey: keys.workspaces, queryFn: api.listWorkspaces })

/** One workspace, read from the list (the API has no single-workspace route). `null` once loaded if it doesn't exist. */
export const useWorkspace = (id: string) =>
  useQuery({
    queryKey: keys.workspaces,
    queryFn: api.listWorkspaces,
    select: (workspaces) => workspaces.find((workspace) => workspace.id === id) ?? null,
  })

/** Turns an imported (read-only) workspace into a normal one, for good. The workspace list is what the page reads from. */
export function useMakeWorkspaceEditable() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.makeWorkspaceEditable(id),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.workspaces }),
  })
}

/** Whether a workspace carries a screening record from an imported package. */
export const usePackageRecord = (workspaceId: string) =>
  useQuery({ queryKey: keys.packageRecord(workspaceId), queryFn: () => api.hasPackageRecord(workspaceId) })

/** Whether the package, with its PDFs when `pdfs`, fits the import cap: a 409 ApiError when it does not. */
export const usePackageFits = (workspaceId: string, pdfs: boolean, answers: boolean) =>
  useQuery({
    queryKey: keys.packageCheck(workspaceId, pdfs, answers),
    queryFn: () => api.checkPackage(workspaceId, pdfs, answers),
    // always: a package too large for the import is refused with or without PDFs (it's cheap without them)
    retry: false, // a 409 is the answer, not a failure to retry
  })

/** Imports a `.paperlab` file as a new workspace; the workspace list refreshes with it. */
export function useImportPackage() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => api.importPackage(file),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.workspaces }),
  })
}

/** A workspace's papers. Polls while one is ingesting, like the library, so an upload from the Papers tab shows progress. */
export const useWorkspacePapers = (id: string) =>
  useQuery({
    queryKey: keys.workspacePapers(id),
    queryFn: () => api.listWorkspacePapers(id),
    refetchInterval: (query) => papersPollInterval(query.state.data),
  })

export function useWorkspaceMutations() {
  const client = useQueryClient()
  const onSuccess = () => client.invalidateQueries({ queryKey: keys.workspaces })
  return {
    create: useMutation({ mutationFn: api.createWorkspace, onSuccess }),
    rename: useMutation({
      mutationFn: ({ id, name }: { id: string; name: string }) => api.renameWorkspace(id, name),
      // The paper page's tag groups carry the workspace name.
      onSuccess: () => Promise.all([onSuccess(), client.invalidateQueries({ predicate: (q) => q.queryKey[0] === 'papers' && q.queryKey[2] === 'tags' })]),
    }),
    remove: useMutation({
      mutationFn: api.deleteWorkspace,
      // Papers keep existing, but their `workspace_ids` lose this workspace.
      // A manuscript in it is left without a workspace.
      onSuccess: () =>
        Promise.all([onSuccess(), client.invalidateQueries({ queryKey: keys.papers }), client.invalidateQueries({ queryKey: keys.manuscripts })]),
    }),
  }
}

type Membership = { workspaceId: string; paperIds: string[]; member: boolean }

/** Adds papers to a workspace (`member: true`) or removes them. Check marks, counts and the workspace's tabs follow. */
export function useWorkspaceMembership() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async ({ workspaceId, paperIds, member }: Membership) => {
      for (const paperId of paperIds) {
        await (member ? api.addToWorkspace(workspaceId, paperId) : api.removeFromWorkspace(workspaceId, paperId))
      }
    },
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.papers }),
        client.invalidateQueries({ queryKey: keys.workspaces }),
      ]),
  })
}
