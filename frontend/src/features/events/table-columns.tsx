import type { ColumnDef } from '@tanstack/react-table'

import { Badge } from '../../components/ui/badge'
import { formatDate, formatPercent } from '../../lib/utils'

import type { EventRecord } from './types'

function statusVariant(status: string) {
  if (status === 'published' || status === 'approved') {
    return 'success'
  }
  if (status === 'rejected') {
    return 'danger'
  }
  if (status === 'needs_review') {
    return 'warning'
  }
  return 'default'
}

export const eventColumns: ColumnDef<EventRecord>[] = [
  {
    accessorKey: 'title',
    header: 'Title',
    cell: ({ row }) => (
      <div>
        <p className="font-medium text-foreground">{row.original.title}</p>
        <p className="text-xs text-muted-foreground">{row.original.object_name_raw}</p>
      </div>
    ),
  },
  {
    accessorKey: 'review_status',
    header: 'Review',
    cell: ({ row }) => <Badge variant={statusVariant(row.original.review_status)}>{row.original.review_status.replace(/_/g, ' ')}</Badge>,
  },
  {
    accessorKey: 'action',
    header: 'Action',
    cell: ({ row }) => row.original.action.replace(/_/g, ' '),
  },
  {
    accessorKey: 'category',
    header: 'Category',
  },
  {
    accessorKey: 'confidence',
    header: 'Confidence',
    cell: ({ row }) => formatPercent(row.original.confidence),
  },
  {
    accessorKey: 'importance',
    header: 'Importance',
  },
  {
    accessorKey: 'source_id',
    header: 'Source',
  },
  {
    accessorKey: 'event_date',
    header: 'Event Date',
    cell: ({ row }) => formatDate(row.original.event_date),
  },
  {
    accessorKey: 'extracted_at',
    header: 'Extracted',
    cell: ({ row }) => formatDate(row.original.extracted_at),
  },
]
