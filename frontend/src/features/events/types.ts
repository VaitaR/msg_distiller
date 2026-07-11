export type ReviewStatus =
  | 'needs_review'
  | 'approved'
  | 'published'
  | 'rejected'
  | 'archived'

export type EventRecord = {
  event_id: string
  message_id: string
  source_channels: string[]
  title: string
  action: string
  object_id: string | null
  object_name_raw: string
  qualifiers: string[]
  stroke: string | null
  anchor: string | null
  category: string
  status: string
  change_type: string
  environment: string
  severity: string | null
  confidence: number
  importance: number
  message_published_at: string | null
  summary: string
  why_it_matters: string | null
  links: string[]
  anchors: string[]
  impact_area: string[]
  impact_type: string[]
  time_source: string
  time_confidence: number
  cluster_key: string
  dedup_key: string
  source_id: string
  review_status: ReviewStatus
  reviewed_by: string | null
  reviewed_at: string | null
  version: number
  origin: string
  extracted_at: string
  planned_start: string | null
  planned_end: string | null
  actual_start: string | null
  actual_end: string | null
  event_date: string | null
}

export type EventListResponse = {
  items: EventRecord[]
  total: number
  limit: number
  offset: number
}

export type ReviewStats = {
  needs_review: number
  approved: number
  published: number
  rejected: number
  archived: number
}

export type TimelineEntry = {
  event_id: string
  title: string
  category: string
  status: string
  review_status: string
  start: string
  end: string | null
  importance: number
  confidence: number
  source_id: string
}

export type TimelineResponse = {
  entries: TimelineEntry[]
  total: number
}

export type ReviewAction = 'approve' | 'reject' | 'publish'

export type ReviewActionInput = {
  eventId: string
  action: ReviewAction
  actor: string
  note?: string
}

export type PatchEventInput = {
  eventId: string
  actor: string
  updates: Partial<Pick<EventRecord, 'title' | 'summary' | 'why_it_matters'>>
}

export type EventListFilters = {
  reviewStatus?: ReviewStatus
  limit?: number
  offset?: number
}

export type TimelineFilters = {
  days: number
  reviewStatus?: ReviewStatus
}

export type AuditEntryRecord = {
  audit_id: string
  event_id: string
  version: number
  action: string
  origin: string
  changes: Record<string, unknown>
  actor: string
  timestamp: string
  note: string | null
}

export type EventRelationRecord = {
  relation_type: string
  target_event_id: string
}

export type EventVersionRecord = {
  version_id: string
  event_id: string
  version: number
  origin: string
  snapshot: Record<string, unknown>
  created_at: string
}

export type MessageMetadataRecord = {
  permalink: string | null
  post_url: string | null
  forwarded_from: string | null
  reply_count: number
  reactions_count: number
  has_file: boolean
  file_mime: string | null
}

export type UnmergeInput = {
  eventId: string
  actor: string
}