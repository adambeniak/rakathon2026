import { formatDate } from '@/lib/date'
import type { TimelineEvent } from '@/lib/domain'
import { StatusPill } from './StatusPill'
import { cn } from '@/lib/cn'

export function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <ol className="relative ml-2 border-l border-hairline">
      {events.map((e) => (
        <li key={`${e.date}-${e.label}`} className="relative pb-5 pl-5">
          <span
            aria-hidden
            className={cn('absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full', e.excluded ? 'bg-stale' : 'bg-accent')}
          />
          <p className="font-mono text-xs text-muted">{formatDate(e.date)}</p>
          <p className={cn('font-medium', e.excluded && 'text-muted')}>
            {e.label} {e.excluded && <StatusPill kind="excluded" className="ml-1" />}
          </p>
          {e.note && <p className="text-xs text-muted">{e.note}</p>}
        </li>
      ))}
    </ol>
  )
}
