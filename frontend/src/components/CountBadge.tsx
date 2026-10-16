import { StatusPill, type PillKind } from './StatusPill'

export function CountBadge({ kind, count }: { kind: Extract<PillKind, 'missing' | 'conflict' | 'stale'>; count: number }) {
  if (count === 0) return null
  return (
    <span className="inline-flex items-center gap-1">
      <StatusPill kind={kind} />
      <span className="font-mono text-sm font-semibold" aria-label={`počet: ${count}`}>
        {count}
      </span>
    </span>
  )
}
