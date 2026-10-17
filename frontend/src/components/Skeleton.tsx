import { cn } from '@/lib/cn'
import { common } from '@/i18n/cs/common'

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('animate-pulse rounded bg-sunken', className)} />
}

export function LoadingBlock({ lines = 3 }: { lines?: number }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <span className="sr-only">{common.loading}</span>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className="h-6 w-full" />
      ))}
    </div>
  )
}
