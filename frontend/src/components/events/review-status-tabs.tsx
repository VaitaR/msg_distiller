import type { ReviewStatus } from '../../features/events/types'
import { cn } from '../../lib/utils'

const tabs: Array<{ value: ReviewStatus | 'all'; label: string }> = [
  { value: 'needs_review', label: 'Needs Review' },
  { value: 'approved', label: 'Approved' },
  { value: 'published', label: 'Published' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'archived', label: 'Archived' },
  { value: 'all', label: 'All' },
]

export function ReviewStatusTabs({
  value,
  onChange,
}: {
  value: ReviewStatus | 'all'
  onChange: (value: ReviewStatus | 'all') => void
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          type="button"
          onClick={() => onChange(tab.value)}
          className={cn(
            'rounded-full px-4 py-2 text-sm font-medium transition',
            value === tab.value
              ? 'bg-primary text-primary-foreground shadow-soft'
              : 'bg-white/70 text-muted-foreground hover:bg-white',
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}