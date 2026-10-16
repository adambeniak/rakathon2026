import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { useDemo } from '@/app/DemoContext'
import { useClaimCase, useInbox } from '@/features/cases/api'
import { inbox as t } from '@/i18n/cs/inbox'
import type { CaseSummary } from '@/lib/domain'
import { InboxCard } from './components/InboxCard'

const COLUMNS = ['new', 'active', 'snoozed'] as const

export function Inbox() {
  const { role } = useDemo()
  const q = useInbox()
  const claim = useClaimCase()
  const canClaim = role === 'coordinator'

  if (q.isPending) return <LoadingBlock lines={6} />
  if (q.isError) return <ErrorState onRetry={() => void q.refetch()} />

  // One primary action per view: only the first unclaimed case offers "Převzít" as a primary button.
  const firstSent = q.data.find((c) => c.state === 'odeslano')?.id

  return (
    <div className="space-y-4">
      <h1 className="text-3xl">{t.title}</h1>
      <div className="grid gap-4 lg:grid-cols-3">
        {COLUMNS.map((col) => {
          const items: CaseSummary[] = q.data.filter((c) => c.column === col)
          return (
            <section key={col} aria-labelledby={`col-${col}`} className="space-y-3 rounded-lg bg-accent-soft/40 p-3">
              <h2 id={`col-${col}`} className="flex items-center justify-between text-xl">
                {t.columns[col]}
                <span className="rounded-full bg-card px-2 font-sans text-sm" aria-label={`počet případů: ${items.length}`}>
                  {t.columnCount(items.length)}
                </span>
              </h2>
              {items.length === 0 && <EmptyState title={t.emptyColumn} hint={t.emptyColumnHint} />}
              {items.map((c) => (
                <InboxCard
                  key={c.id}
                  c={c}
                  claiming={claim.isPending}
                  onClaim={canClaim && c.id === firstSent ? (id) => claim.mutate(id) : undefined}
                />
              ))}
            </section>
          )
        })}
      </div>
    </div>
  )
}
