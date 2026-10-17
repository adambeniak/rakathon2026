import { Link, useParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { StatusPill, type PillKind } from '@/components/StatusPill'
import { Button } from '@/components/ui/button'
import { cases as t } from '@/i18n/cs/cases'
import { formatDate } from '@/lib/date'
import type { Finding } from '@/lib/domain'
import { useDemo } from '@/app/DemoContext'
import { useTasks } from '@/features/coordination/api'
import { useCase, useFindings } from '../api'
import { TriagePanel } from './TriagePanel'

const ORDER: Finding['bucket'][] = ['missing', 'conflict', 'stale', 'document', 'info']
const PILL: Partial<Record<Finding['bucket'], PillKind>> = { missing: 'missing', conflict: 'conflict', stale: 'stale' }

export function Overview() {
  const { id = '' } = useParams()
  const findings = useFindings(id)
  const tasks = useTasks(id)
  const c = useCase(id)
  const { role } = useDemo()
  const triage = c.data?.state === 'triage' || c.data?.state === 'ceka_na_podklady'

  return (
    <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
      <section aria-labelledby="findings-h" className="space-y-4">
        {triage && <TriagePanel caseId={id} canAct={role === 'coordinator'} />}
        <div className="flex items-center justify-between gap-4">
          <h2 id="findings-h" className="text-2xl">
            {t.overview.findings}
          </h2>
          {/* The header already carries the case's primary action while a state-specific one exists. */}
          <Button asChild variant="secondary">
            <Link to={`/cases/${id}/handover`}>{t.overview.openHandover}</Link>
          </Button>
        </div>
        {findings.isPending && <LoadingBlock />}
        {findings.isError && <ErrorState onRetry={() => void findings.refetch()} />}
        {findings.data?.length === 0 && <EmptyState title={t.overview.noFindings} hint={t.overview.noFindingsHint} />}
        {findings.data &&
          ORDER.map((bucket) => {
            const items = findings.data.filter((f) => f.bucket === bucket)
            if (items.length === 0) return null
            const pill = PILL[bucket]
            return (
              <div key={bucket} className="space-y-2">
                <h3 className="flex items-center gap-2 text-base">
                  {pill && <StatusPill kind={pill} />}
                  {t.overview.buckets[bucket]}
                </h3>
                <ul className="space-y-2">
                  {items.map((f) => (
                    <li key={f.id} className="rounded border border-hairline bg-card p-3">
                      <p className="font-medium">{f.title}</p>
                      <p className="text-sm text-muted">{f.detail}</p>
                      {f.quotes.map((q) => (
                        <blockquote key={q} className="mt-1 border-l-2 border-accent pl-2 font-mono text-xs">
                          <span className="sr-only">{t.overview.quoteLabel}: </span>
                          {q}
                        </blockquote>
                      ))}
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
      </section>
      <section aria-labelledby="steps-h" className="space-y-2">
        <h2 id="steps-h" className="text-2xl">
          {t.overview.nextSteps}
        </h2>
        {tasks.isPending && <LoadingBlock lines={2} />}
        {tasks.data && tasks.data.filter((x) => x.state !== 'done').length === 0 && (
          <p className="text-muted">{t.overview.noSteps}</p>
        )}
        <ul className="space-y-2">
          {tasks.data
            ?.filter((x) => x.state !== 'done')
            .slice(0, 4)
            .map((x) => (
              <li key={x.id} className="rounded border border-hairline bg-card p-3 text-sm">
                <p className="font-medium">{x.title}</p>
                <p className="text-muted">
                  {x.owner} · {formatDate(x.due)}
                  {x.state === 'overdue' && <span className="ml-1 font-semibold text-missing">({t.tasks.state.overdue})</span>}
                </p>
              </li>
            ))}
        </ul>
      </section>
    </div>
  )
}
