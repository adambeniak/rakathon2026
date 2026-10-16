import type { ReactNode } from 'react'
import { Inbox } from 'lucide-react'
import { common } from '@/i18n/cs/common'

export function EmptyState({ title, hint, action }: { title: string; hint: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-hairline bg-card px-6 py-10 text-center">
      <Inbox aria-hidden className="h-6 w-6 text-muted" />
      <p className="font-serif text-xl">{title}</p>
      <p className="max-w-md text-muted">{hint}</p>
      {action}
    </div>
  )
}

export function ErrorState({ onRetry }: { onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-missing/40 bg-missing-bg p-4 text-missing">
      {common.error}
      {onRetry && (
        <button type="button" onClick={onRetry} className="ml-3 underline">
          {common.retry}
        </button>
      )}
    </div>
  )
}
