import { Link, useParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { StatusPill } from '@/components/StatusPill'
import { Button } from '@/components/ui/button'
import { useDemo } from '@/app/DemoContext'
import { useDocuments, useFindings } from '@/features/cases/api'
import { handover as t } from '@/i18n/cs/handover'
import { formatDateTime } from '@/lib/date'
import { SectionCard } from './components/SectionCard'
import { useConfirmAll, useConfirmSection, useHandover } from './api'

export function Handover() {
  const { id = '' } = useParams()
  const { role } = useDemo()
  const isPhysician = role === 'physician'
  const q = useHandover(id)
  const docs = useDocuments(id)
  const findings = useFindings(id)
  const confirm = useConfirmSection(id)
  const confirmAll = useConfirmAll(id)

  if (q.isPending) return <LoadingBlock lines={8} />
  if (q.isError) return <ErrorState onRetry={() => void q.refetch()} />
  if (q.data.sections.length === 0) return <EmptyState title={t.empty} hint={t.emptyHint} />

  const confirmable = q.data.sections.filter((s) => s.status !== 'missing')
  const done = confirmable.filter((s) => s.confirmed).length

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl">{t.title}</h2>
          <p className="text-sm text-muted">
            {t.asOf}: {formatDateTime(q.data.asOf)} · {t.sectionsDone(done, confirmable.length)}
          </p>
          {!isPhysician && <p className="text-sm text-conflict">{t.physicianOnly}</p>}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" disabled={!isPhysician || confirmAll.isPending || done === confirmable.length}
            title={isPhysician ? undefined : t.physicianOnly} onClick={() => confirmAll.mutate()}>
            {t.confirmAll}
          </Button>
          <Button asChild variant="primary">
            <Link to={`/cases/${id}/mdt`}>{t.prepareMdt}</Link>
          </Button>
        </div>
      </div>

      {q.data.sections.map((s) => (
        <SectionCard
          key={s.key}
          s={s}
          docs={docs.data ?? []}
          findings={(findings.data ?? []).filter((f) => s.findingIds.includes(f.id))}
          busy={confirm.isPending}
          canConfirm={isPhysician}
          onConfirm={(key) => confirm.mutate(key)}
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
                <StatusPill kind="excluded" /> <span className="font-mono text-xs">{d.id.slice(0, 2)}</span> {d.title}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
