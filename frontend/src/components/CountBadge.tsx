import { StatusPill, type PillKind } from './StatusPill'

export function CountBadge({ kind, count }: { kind: Extract<PillKind, 'missing' | 'conflict' | 'stale'>; count: number | null }) {
  if (count === 0) return null
  if (count === null) {
    return (
      <span className="inline-flex items-center gap-1.5 text-muted">
        <StatusPill kind={kind} />
        <span className="font-mono text-sm" aria-label="počet zatím nespočítán">
          —
        </span>
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      <StatusPill kind={kind} />
      <span className="font-mono text-sm font-semibold" aria-label={`počet: ${count}`}>
        {count}
      </span>
    </span>
  )
}
