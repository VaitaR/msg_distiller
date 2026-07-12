import { Sparkles } from 'lucide-react'

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="glass-card flex min-h-48 flex-col items-center justify-center gap-3 p-8 text-center">
      <Sparkles className="size-10 text-primary/70" />
      <div>
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  )
}
