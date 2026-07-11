import type { ReviewStats } from '../../features/events/types'
import { Badge } from '../ui/badge'
import { Card, CardContent } from '../ui/card'

const statsConfig = [
  { key: 'needs_review', label: 'Needs Review', variant: 'warning' as const },
  { key: 'approved', label: 'Approved', variant: 'success' as const },
  { key: 'published', label: 'Published', variant: 'info' as const },
  { key: 'rejected', label: 'Rejected', variant: 'danger' as const },
  { key: 'archived', label: 'Archived', variant: 'default' as const },
]

export function ReviewStatsBar({ stats }: { stats: ReviewStats }) {
  return (
    <Card>
      <CardContent className="flex flex-wrap gap-3">
        {statsConfig.map((item) => (
          <Badge key={item.key} variant={item.variant} className="px-4 py-2 text-sm">
            {item.label}: {stats[item.key as keyof ReviewStats]}
          </Badge>
        ))}
      </CardContent>
    </Card>
  )
}