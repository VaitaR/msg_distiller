import type { ReviewStatus } from '../../features/events/types'

import { Card, CardContent } from '../ui/card'

export function TimelineFilters({
  days,
  reviewStatus,
  onDaysChange,
  onReviewStatusChange,
}: {
  days: number
  reviewStatus: ReviewStatus | 'all'
  onDaysChange: (days: number) => void
  onReviewStatusChange: (status: ReviewStatus | 'all') => void
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-4 md:flex-row md:items-center">
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium" htmlFor="days-filter">
            Range
          </label>
          <select
            id="days-filter"
            className="rounded-full border border-input bg-white/80 px-4 py-2 text-sm"
            value={days}
            onChange={(event) => onDaysChange(Number(event.target.value))}
          >
            {[7, 14, 30, 60, 90].map((option) => (
              <option key={option} value={option}>
                {option} days
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium" htmlFor="timeline-status-filter">
            Review state
          </label>
          <select
            id="timeline-status-filter"
            className="rounded-full border border-input bg-white/80 px-4 py-2 text-sm"
            value={reviewStatus}
            onChange={(event) => onReviewStatusChange(event.target.value as ReviewStatus | 'all')}
          >
            <option value="all">All</option>
            <option value="published">Published</option>
            <option value="approved">Approved</option>
            <option value="needs_review">Needs review</option>
            <option value="rejected">Rejected</option>
            <option value="archived">Archived</option>
          </select>
        </div>
      </CardContent>
    </Card>
  )
}