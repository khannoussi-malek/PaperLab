import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { keys } from './core'

export const useTags = (ws: string) => useQuery({ queryKey: keys.tags(ws), queryFn: () => api.listTags(ws) })

export const usePaperTags = (ws: string) => useQuery({ queryKey: keys.paperTags(ws), queryFn: () => api.paperTags(ws) })

export const usePaperTagGroups = (paperId: string) =>
  useQuery({ queryKey: keys.paperTagsOfPaper(paperId), queryFn: () => api.tagsOfPaper(paperId) })

/** Every tag change can alter the sidebar counts, each paper's chips and the paper page's groups. */
function invalidateTags(client: QueryClient, ws: string) {
  return Promise.all([
    client.invalidateQueries({ queryKey: keys.tags(ws) }),
    client.invalidateQueries({ queryKey: keys.paperTags(ws) }),
    client.invalidateQueries({ predicate: (q) => q.queryKey[0] === 'papers' && q.queryKey[2] === 'tags' }),
  ])
}

type TagChange = { tag: string; paperIds: string[] }

export function useApplyTag(ws: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ tag, paperIds }: TagChange) => api.applyTag(ws, tag, paperIds),
    onSuccess: () => invalidateTags(client, ws),
  })
}

export function useRemoveTag(ws: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ tag, paperIds }: TagChange) => api.removeTag(ws, tag, paperIds),
    onSuccess: () => invalidateTags(client, ws),
  })
}

export function useRenameTag(ws: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ tagId, newName }: { tagId: string; newName: string }) => api.renameTag(ws, tagId, newName),
    onSuccess: () => invalidateTags(client, ws),
  })
}

export function useDeleteTag(ws: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (tagId: string) => api.deleteTag(ws, tagId),
    onSuccess: () => invalidateTags(client, ws),
  })
}
