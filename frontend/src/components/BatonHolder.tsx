import { Hourglass } from 'lucide-react'
import { common } from '@/i18n/cs/common'
import type { BatonHolderInfo } from '@/lib/domain'
import { daysUntil, formatDate, formatRemaining } from '@/lib/date'
import { useDemo } from '@/app/DemoContext'
import { cn } from '@/lib/cn'

export function BatonHolder({ baton, size = 'sm' }: { baton: BatonHolderInfo; size?: 'sm' | 'lg' }) {
  const { today } = useDemo()
  const days = baton.due ? daysUntil(baton.due, today) : null
  const overdue = days !== null && days < 0
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
            {common.baton.deadline}: {formatDate(baton.due)} ({formatRemaining(days ?? 0)})
          </>
        ) : (
          common.baton.none
        )}
      </p>
    </div>
  )
}
