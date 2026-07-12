import { apiClient } from '../../lib/api/client'

import type {
  AuditEntryRecord,
  EventListFilters,
  EventListResponse,
  EventRelationRecord,
  EventRecord,
  EventVersionRecord,
  MessageMetadataRecord,
  PatchEventInput,
  ReviewActionInput,
  ReviewStats,
  TimelineFilters,
  TimelineResponse,
  UnmergeInput,
} from './types'

export const eventsApi = {
  list: (filters: EventListFilters) =>
    apiClient.get<EventListResponse>('/api/v1/events', {
      review_status: filters.reviewStatus,
      limit: filters.limit ?? 200,
      offset: filters.offset ?? 0,
    }),
  stats: () => apiClient.get<ReviewStats>('/api/v1/events/stats'),
  detail: (eventId: string) => apiClient.get<EventRecord>(`/api/v1/events/${eventId}`),
  audit: (eventId: string) => apiClient.get<AuditEntryRecord[]>(`/api/v1/events/${eventId}/audit`),
  relations: (eventId: string) => apiClient.get<EventRelationRecord[]>(`/api/v1/events/${eventId}/relations`),
  versions: (eventId: string) => apiClient.get<EventVersionRecord[]>(`/api/v1/events/${eventId}/versions`),
  messageMetadata: (eventId: string) =>
    apiClient.get<MessageMetadataRecord>(`/api/v1/events/${eventId}/message-metadata`),
  timeline: (filters: TimelineFilters) =>
    apiClient.get<TimelineResponse>('/api/v1/events/timeline', {
      days: filters.days,
      review_status: filters.reviewStatus,
    }),
  review: ({ eventId, ...body }: ReviewActionInput) =>
    apiClient.post<{ status: string }>(`/api/v1/events/${eventId}/review`, body),
  unmerge: ({ eventId, ...body }: UnmergeInput) =>
    apiClient.post<{ status: string; restored_event_ids: string[] }>(`/api/v1/events/${eventId}/unmerge`, body),
  patch: ({ eventId, ...body }: PatchEventInput) =>
    apiClient.patch<{ status: string }>(`/api/v1/events/${eventId}`, body),
}
