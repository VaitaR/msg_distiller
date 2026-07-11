import { useMutation, useQueryClient } from '@tanstack/react-query'

import { eventsApi } from './api'
import { eventKeys } from './queries'
import type { PatchEventInput, ReviewActionInput, UnmergeInput } from './types'

export function useReviewActionMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: ReviewActionInput) => eventsApi.review(input),
    onSuccess: async (_, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: eventKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: eventKeys.stats() }),
        queryClient.invalidateQueries({ queryKey: eventKeys.detail(variables.eventId) }),
        queryClient.invalidateQueries({ queryKey: eventKeys.all }),
      ])
    },
  })
}

export function usePatchEventMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: PatchEventInput) => eventsApi.patch(input),
    onSuccess: async (_, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: eventKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: eventKeys.detail(variables.eventId) }),
        queryClient.invalidateQueries({ queryKey: eventKeys.audit(variables.eventId) }),
        queryClient.invalidateQueries({ queryKey: eventKeys.versions(variables.eventId) }),
        queryClient.invalidateQueries({ queryKey: [...eventKeys.all, 'timeline'] }),
      ])
    },
  })
}

export function useUnmergeMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: UnmergeInput) => eventsApi.unmerge(input),
    onSuccess: async (_, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: eventKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: eventKeys.stats() }),
        queryClient.invalidateQueries({ queryKey: eventKeys.detail(variables.eventId) }),
        queryClient.invalidateQueries({ queryKey: eventKeys.relations(variables.eventId) }),
        queryClient.invalidateQueries({ queryKey: eventKeys.all }),
      ])
    },
  })
}