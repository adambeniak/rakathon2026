import type { ReactNode } from 'react'
import { Inbox } from 'lucide-react'
import { common } from '@/i18n/cs/common'

export function EmptyState({ title, hint, action }: { title: string; hint: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 border-y border-hairline px-6 py-12 text-center">
      <Inbox aria-hidden className="h-8 w-8 text-muted" strokeWidth={1.75} />
      <p className="text-xl font-semibold">{title}</p>
      <p className="max-w-prose text-muted">{hint}</p>
      {action}
    </div>
  )
}

export function ErrorState({ onRetry }: { onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border-l-4 border-missing bg-missing-bg px-5 py-4 font-medium text-missing">
      {common.error}
      {onRetry && (
        <button type="button" onClick={onRetry} className="inline-flex min-h-10 items-center rounded-md border-[1.5px] border-missing px-4 text-sm font-semibold hover:bg-card">
          {common.retry}
        </button>
      )}
    </div>
  )
}
