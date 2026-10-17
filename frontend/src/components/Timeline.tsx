import { formatDate } from '@/lib/date'
import type { TimelineEvent } from '@/lib/domain'
import { StatusPill } from './StatusPill'
import { cn } from '@/lib/cn'

export function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <ol className="relative ml-2 border-l-2 border-hairline">
      {events.map((e) => (
        <li key={`${e.date}-${e.label}`} className="relative pb-6 pl-6">
          <span
            aria-hidden
            className={cn('absolute -left-[7px] top-1 h-3 w-3 rounded-full ring-4 ring-surface', e.excluded ? 'bg-stale' : 'bg-accent')}
          />
          <p className="text-xs text-muted">{formatDate(e.date)}</p>
          <p className={cn('font-semibold', e.excluded && 'font-medium text-muted')}>
            {e.label} {e.excluded && <StatusPill kind="excluded" className="ml-1" />}
          </p>
          {e.note && <p className="text-sm text-muted">{e.note}</p>}
        </li>
      ))}
    </ol>
  )
}
