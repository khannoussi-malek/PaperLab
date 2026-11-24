import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { keys } from './core'

/** Every library paper and the links between them, in one request (D109): layers and focus need no further calls. */
export const useLibraryGraph = (workspaceId: string | null) =>
  useQuery({
    queryKey: keys.libraryGraph(workspaceId),
    queryFn: () => api.libraryGraph(workspaceId),
    placeholderData: keepPreviousData,
  })

/** The owner's own links. Each write refetches the graph, which carries them. Save and remove report separately. */
export function usePaperLinkMutations() {
  const client = useQueryClient()
  const onSuccess = () => client.invalidateQueries({ queryKey: keys.graph })
  const create = useMutation({
    mutationFn: ({ from, to, label }: { from: string; to: string; label: string }) =>
      api.createPaperLink(from, to, label),
    onSuccess,
  })
  const rename = useMutation({
    mutationFn: ({ id, label }: { id: string; label: string }) => api.renamePaperLink(id, label),
    onSuccess,
  })
  const remove = useMutation({ mutationFn: api.deletePaperLink, onSettled: onSuccess })
  return {
    create,
    rename,
    remove,
    /** The dialog shows these two; the panel shows a failed removal, which has no dialog. */
    saveError: (create.error ?? rename.error)?.message ?? null,
    removeError: remove.error?.message ?? null,
  }
}
