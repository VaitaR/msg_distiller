import { useQuery } from '@tanstack/react-query'

import { eventsApi } from './api'
import type { EventListFilters, TimelineFilters } from './types'

export const eventKeys = {
  all: ['events'] as const,
  lists: () => [...eventKeys.all, 'list'] as const,
  list: (filters: EventListFilters) => [...eventKeys.lists(), filters] as const,
  stats: () => [...eventKeys.all, 'stats'] as const,
  details: () => [...eventKeys.all, 'detail'] as const,
  detail: (eventId: string) => [...eventKeys.details(), eventId] as const,
  audits: () => [...eventKeys.all, 'audit'] as const,
  audit: (eventId: string) => [...eventKeys.audits(), eventId] as const,
  relations: (eventId: string) => [...eventKeys.all, 'relations', eventId] as const,
  versions: (eventId: string) => [...eventKeys.all, 'versions', eventId] as const,
  messageMetadata: (eventId: string) => [...eventKeys.all, 'message-metadata', eventId] as const,
  timeline: (filters: TimelineFilters) => [...eventKeys.all, 'timeline', filters] as const,
}

export function useEvents(filters: EventListFilters) {
  return useQuery({
    queryKey: eventKeys.list(filters),
    queryFn: () => eventsApi.list(filters),
    refetchInterval: 30_000,
  })
}

export function useReviewStats() {
  return useQuery({
    queryKey: eventKeys.stats(),
    queryFn: eventsApi.stats,
    refetchInterval: 30_000,
  })
}

export function useEventDetail(eventId: string | null) {
  return useQuery({
    queryKey: eventKeys.detail(eventId ?? 'none'),
    queryFn: () => eventsApi.detail(eventId ?? ''),
    enabled: Boolean(eventId),
  })
}

export function useEventAudit(eventId: string | null) {
  return useQuery({
    queryKey: eventKeys.audit(eventId ?? 'none'),
    queryFn: () => eventsApi.audit(eventId ?? ''),
    enabled: Boolean(eventId),
  })
}

export function useEventRelations(eventId: string | null) {
  return useQuery({
    queryKey: eventKeys.relations(eventId ?? 'none'),
    queryFn: () => eventsApi.relations(eventId ?? ''),
    enabled: Boolean(eventId),
  })
}

export function useEventVersions(eventId: string | null) {
  return useQuery({
    queryKey: eventKeys.versions(eventId ?? 'none'),
    queryFn: () => eventsApi.versions(eventId ?? ''),
    enabled: Boolean(eventId),
  })
}

export function useEventMessageMetadata(eventId: string | null) {
  return useQuery({
    queryKey: eventKeys.messageMetadata(eventId ?? 'none'),
    queryFn: () => eventsApi.messageMetadata(eventId ?? ''),
    enabled: Boolean(eventId),
  })
}

export function useTimeline(filters: TimelineFilters) {
  return useQuery({
    queryKey: eventKeys.timeline(filters),
    queryFn: () => eventsApi.timeline(filters),
    refetchInterval: 30_000,
  })
}
