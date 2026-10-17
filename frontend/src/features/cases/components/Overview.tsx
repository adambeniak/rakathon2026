import { Link, useParams } from 'react-router-dom'
import { LoadingBlock } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { cases as t } from '@/i18n/cs/cases'
import { coordination as tc } from '@/i18n/cs/coordination'
import { formatDate } from '@/lib/date'
import { useDemo } from '@/app/DemoContext'
import { useTasks } from '@/features/coordination/api'
import { useCase } from '../api'
import { TriagePanel } from './TriagePanel'

export function Overview() {
  const { id = '' } = useParams()
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
        <p className="text-muted">{t.overview.findingsHint}</p>
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
                  {x.owner ?? tc.task.ownerUnassigned} · {formatDate(x.due)}
                  {x.state === 'overdue' && <span className="ml-1 font-semibold text-missing">({t.tasks.state.overdue})</span>}
                </p>
              </li>
            ))}
        </ul>
      </section>
    </div>
  )
}
