import { Hourglass } from 'lucide-react'
import { common } from '@/i18n/cs/common'
import type { BatonHolderInfo } from '@/lib/domain'
import { daysUntil, formatDate, formatRemaining } from '@/lib/date'
import { useDemo } from '@/app/DemoContext'
import { cn } from '@/lib/cn'

interface BatonHolderProps {
  baton: BatonHolderInfo | null
  size?: 'sm' | 'lg'
  /** Overdue flag from the API; when given, the UI does not derive it from the dates. */
  overdue?: boolean
  /** The API clock (e.g. `Board.computed_at`) the countdown is measured from; defaults to the demo date. */
  now?: string
}

export function BatonHolder({ baton, size = 'sm', overdue: apiOverdue, now }: BatonHolderProps) {
  const { today } = useDemo()
  if (!baton) {
    return (
      <p className={cn('flex items-center gap-1.5', size === 'lg' ? 'text-base' : 'text-sm')}>
        <Hourglass aria-hidden className="h-4 w-4 shrink-0 text-accent" />
        <span className="text-muted">
          {common.baton.label}: {common.baton.nobody}
        </span>
      </p>
    )
  }
  const days = baton.due ? daysUntil(baton.due, now ?? today) : null
  const overdue = apiOverdue ?? (days !== null && days < 0)
  return (
    <div className={cn(size === 'lg' ? 'text-base' : 'text-sm')}>
      <p className="flex items-center gap-1.5">
        <Hourglass aria-hidden className="h-4 w-4 shrink-0 text-accent" />
        <span>
          <span className="text-muted">{common.baton.label}: </span>
          <strong className="font-semibold">{baton.name}</strong>
        </span>
      </p>
      <p className="ml-[22px] text-muted">{baton.action}</p>
      <p className={cn('ml-[22px]', overdue && 'font-semibold text-missing')}>
        {baton.due ? (
          <>
            {common.baton.deadline} {formatDate(baton.due)} ({formatRemaining(days ?? 0)})
          </>
        ) : (
          common.baton.none
        )}
      </p>
    </div>
  )
}
