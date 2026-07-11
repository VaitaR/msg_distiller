export function LoadingState({ lines = 3 }: { lines?: number }) {
  return (
    <div className="glass-card space-y-4 p-6">
      {Array.from({ length: lines }).map((_, index) => (
        <div key={index} className="h-4 animate-pulse rounded-full bg-secondary" />
      ))}
    </div>
  )
}