import { AlertTriangle } from 'lucide-react'

import { Button } from '../ui/button'

export function ErrorState({
  title,
  description,
  onRetry,
}: {
  title: string
  description: string
  onRetry?: () => void
}) {
  return (
    <div className="glass-card flex min-h-48 flex-col items-center justify-center gap-4 p-8 text-center">
      <AlertTriangle className="size-10 text-destructive" />
      <div>
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      {onRetry ? (
        <Button variant="outline" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  )
}
