import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import type { LLMConnectionUpdate, SkillUpdate } from '@/entities'
import { keys } from './core'

/** The models chat can use, for the dropdown. */
export const useChatModels = () => useQuery({ queryKey: keys.chatModels, queryFn: api.listChatModels })

/** The skills a chat of this kind can use; hidden ones come back only for Settings (`includeHidden`). */
/** `enabled: false` for a chat that offers no skills (a search hit's), so it never asks. */
export const useSkills = (kind: 'paper' | 'workspace', includeHidden = false, enabled = true) =>
  useQuery({
    queryKey: [...keys.skills, kind, includeHidden] as const,
    queryFn: () => api.listSkills(kind, includeHidden),
    enabled,
  })

/** Every skill mutation refetches all skills lists: a change moves rows between kinds, hidden lists and defaults. */
function useSkillMutation<Variables, Result>(mutationFn: (variables: Variables) => Promise<Result>) {
  const client = useQueryClient()
  return useMutation({ mutationFn, onSuccess: () => client.invalidateQueries({ queryKey: keys.skills }) })
}

export const useCreateSkill = () => useSkillMutation(api.createSkill)
export const useUpdateSkill = () =>
  useSkillMutation(({ id, ...body }: { id: string } & SkillUpdate) => api.updateSkill(id, body))
export const useDeleteSkill = () => useSkillMutation(api.deleteSkill)
export const useResetSkill = () => useSkillMutation(api.resetSkill)
export const useSetSkillDefault = () =>
  useSkillMutation(({ id, scope, on }: { id: string; scope: 'paper' | 'workspace'; on: boolean }) =>
    api.setSkillDefault(id, scope, on),
  )

export const useConnections = () => useQuery({ queryKey: keys.connections, queryFn: api.listConnections })

/** A provider's own model list, fetched only while the Add model picker is open. */
export const useAvailableModels = (connectionId: string, enabled: boolean) =>
  useQuery({ queryKey: keys.available(connectionId), queryFn: () => api.availableModels(connectionId), enabled })

/** For streams that aren't mutations (a chat refusal, a finished pull): refetch connections and chat models. */
export function useInvalidateModels() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: keys.llm })
}

export function useConnectionMutations() {
  const client = useQueryClient()
  const onSuccess = () => client.invalidateQueries({ queryKey: keys.llm })
  return {
    create: useMutation({ mutationFn: api.createConnection, onSuccess }),
    update: useMutation({
      mutationFn: ({ id, ...body }: { id: string } & LLMConnectionUpdate) => api.updateConnection(id, body),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: api.deleteConnection, onSuccess }),
    test: useMutation({ mutationFn: api.testConnection }),
    addModel: useMutation({
      mutationFn: ({ connectionId, name }: { connectionId: string; name: string }) => api.addModel(connectionId, name),
      onSuccess,
    }),
    removeModel: useMutation({ mutationFn: api.removeModel, onSuccess }),
    setDefault: useMutation({ mutationFn: api.setDefaultModel, onSuccess }),
    deleteInstalled: useMutation({
      mutationFn: ({ connectionId, name }: { connectionId: string; name: string }) =>
        api.deleteInstalledModel(connectionId, name),
      onSuccess,
    }),
  }
}
