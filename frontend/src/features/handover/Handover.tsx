import { Link, useParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { StatusPill } from '@/components/StatusPill'
import { Button } from '@/components/ui/button'
import { useDemo } from '@/app/DemoContext'
import { useCase } from '@/features/cases/api'
import { useDocuments } from '@/features/documents/api'
import { handover as t } from '@/i18n/cs/handover'
import { problemTitle } from '@/lib/api/problem'
import { formatDateTime } from '@/lib/date'
import { SectionCard } from './components/SectionCard'
import { useHandover, useReviewSection } from './api'

export function Handover() {
  const { id = '' } = useParams()
  const { role } = useDemo()
  const isPhysician = role === 'physician'
  const q = useHandover(id)
  const docs = useDocuments(id)
  const caseQ = useCase(id)
  const review = useReviewSection(id)

  if (q.isPending) return <LoadingBlock lines={8} />
  if (q.isError) return <ErrorState onRetry={() => void q.refetch()} />
  if (q.data.sections.length === 0) return <EmptyState title={t.empty} hint={t.emptyHint} />

  // The Composition is final when every one of the sections is confirmed or accepted as missing.
  const total = q.data.sections.length
  const done = q.data.sections.filter((x) => x.confirmed).length
  // The draft label stays until the server has recorded the last confirmation (review.isPending).
  const allConfirmed = done === total && !review.isPending
  const accepted = q.data.sections.filter((x) => x.acceptedMissing).length
  // Same numbers as the case header; not computed / still loading shows "—", never 0.
  const counts = { missing: caseQ.data?.counts.missing ?? null, conflict: caseQ.data?.counts.conflict ?? null }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl">{t.title}</h2>
          <p className="text-sm text-muted">
            {t.asOf}: {formatDateTime(q.data.asOf)}
          </p>
          {!isPhysician && <p className="text-sm text-conflict">{t.physicianOnly}</p>}
        </div>
        <div className="flex items-center gap-2">
          {/* Primary only once every section is confirmed, so the primary action never invites skipping confirmation. */}
          <Button asChild variant={allConfirmed ? 'primary' : 'secondary'}>
            <Link to={`/cases/${id}/mdt`}>{t.prepareMdt}</Link>
          </Button>
        </div>
      </div>

      <div
        role="group"
        aria-label={t.summary}
        className="sticky top-0 z-30 flex flex-wrap items-center gap-x-5 gap-y-1 rounded-lg border border-hairline bg-card/95 px-4 py-2 shadow-sm backdrop-blur"
      >
        <span className="font-medium">{t.confirmedCount(done, total)}</span>
        <span className="inline-flex items-center gap-1.5">
          <StatusPill kind="missing" />
          <span className="font-mono text-sm font-semibold">{counts.missing ?? '—'}</span>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <StatusPill kind="conflict" />
          <span className="font-mono text-sm font-semibold">{counts.conflict ?? '—'}</span>
        </span>
        {review.isError && (
          <span role="alert" className="text-sm text-missing">
            {t.actionError(problemTitle(review.error))}
          </span>
        )}
        <span className="ml-auto">
          {review.isPending && (
            <span role="status" className="mr-2 text-sm text-muted">
              {t.saving}
            </span>
          )}
          {allConfirmed ? (
            <span role="status" className="text-sm font-medium text-verified">
              {t.allConfirmed(accepted)}
            </span>
          ) : (
            <StatusPill kind="ai" label={t.draftLabel} />
          )}
        </span>
      </div>

      {q.data.sections.map((s) => (
        <SectionCard
          key={s.key}
          s={s}
          editError={review.isError && review.variables?.kind === 'edit' && review.variables.section.key === s.key}
          onReview={(r) => review.mutateAsync(r)}
          docs={docs.data ?? []}
          busy={review.isPending}
          saving={review.isPending && review.variables?.section.key === s.key}
          canConfirm={isPhysician}
        />
      ))}

      {q.data.excluded.length > 0 && (
        <section aria-labelledby="excl-h" className="rounded-lg border border-dashed border-hairline bg-stale-bg/40 p-4">
          <h2 id="excl-h" className="text-xl">
            {t.excludedTitle}
          </h2>
          <p className="text-sm text-muted">{t.excludedHint}</p>
          <ul className="mt-2 space-y-1">
            {q.data.excluded.map((d) => (
              <li key={d.id}>
                <StatusPill kind="excluded" /> <span className="font-mono text-xs">{d.id.slice(0, 2)}</span>{' '}
                {docs.data?.find((x) => x.id === d.id)?.title ?? d.id} <span className="text-sm text-muted">· {d.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
