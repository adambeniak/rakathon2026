import { formatDate, formatDateTime } from '@/lib/date'
import { StatusPill } from './StatusPill'
import { cn } from '@/lib/cn'

/** One row of a timeline, already labelled in Czech; `excluded` and `planned` are decided by the API. */
export interface TimelineItem {
  id: string
  at: string // ISO timestamp
  dateOnly: boolean
  label: string
  notes: string[]
  excluded: boolean
  excludedLabel?: string
  planned: boolean
  plannedLabel?: string
}

export function Timeline({ events }: { events: TimelineItem[] }) {
  return (
    <ol className="relative ml-2 border-l border-hairline">
      {events.map((e) => (
        <li key={e.id} className="relative pb-5 pl-5">
          <span
            aria-hidden
            className={cn(
              'absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full',
              e.excluded ? 'bg-stale' : e.planned ? 'border border-accent bg-card' : 'bg-accent',
            )}
          />
          <p className="font-mono text-xs text-muted">
            <time dateTime={e.at}>{e.dateOnly ? formatDate(e.at) : formatDateTime(e.at)}</time>
            {e.planned && e.plannedLabel && <span> · {e.plannedLabel}</span>}
          </p>
          <p className={cn('font-medium', e.excluded && 'text-muted')}>
            {e.label} {e.excluded && <StatusPill kind="excluded" className="ml-1" />}
          </p>
          {e.excluded && e.excludedLabel && <p className="text-xs text-muted">{e.excludedLabel}</p>}
          {e.notes.map((note) => (
            <p key={note} className="text-xs text-muted">
              {note}
            </p>
          ))}
        </li>
      ))}
    </ol>
  )
}
