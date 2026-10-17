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
    <ol className="relative ml-2 border-l-2 border-hairline">
      {events.map((e) => (
        <li key={e.id} className="relative pb-6 pl-6">
          <span
            aria-hidden
            className={cn(
              'absolute -left-[7px] top-1 h-3 w-3 rounded-full ring-4 ring-surface',
              e.excluded ? 'bg-stale' : e.planned ? 'border-2 border-accent bg-card' : 'bg-accent',
            )}
          />
          <p className="text-xs text-muted">
            <time dateTime={e.at}>{e.dateOnly ? formatDate(e.at) : formatDateTime(e.at)}</time>
            {e.planned && e.plannedLabel && <span> · {e.plannedLabel}</span>}
          </p>
          <p className={cn('font-semibold', e.excluded && 'font-medium text-muted')}>
            {e.label} {e.excluded && <StatusPill kind="excluded" className="ml-1" />}
          </p>
          {e.excluded && e.excludedLabel && <p className="text-sm text-muted">{e.excludedLabel}</p>}
          {e.notes.map((note) => (
            <p key={note} className="text-sm text-muted">
              {note}
            </p>
          ))}
        </li>
      ))}
    </ol>
  )
}
