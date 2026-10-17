import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { BatonHolder } from '@/components/BatonHolder'
import { CaseStateBadge } from '@/components/CaseStateBadge'
import { CountBadge } from '@/components/CountBadge'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { gp as t } from '@/i18n/cs/gp'
import { problemTitle } from '@/lib/api/problem'
import { formatDateTime } from '@/lib/date'
import type { CaseSummary } from '@/lib/domain'
import { useGpCases, useGpOpened, useMdtConclusion } from './api'

/** The signed conclusion. Opening it (a successful read) records the GP's read receipt once per opening. */
function Conclusion({ caseId }: { caseId: string }) {
  const conclusion = useMdtConclusion(caseId, true)
  const opened = useGpOpened()
  const recorded = useRef(false)
  const { mutate } = opened

  useEffect(() => {
    if (!conclusion.isSuccess || recorded.current) return
    recorded.current = true
    mutate(caseId)
  }, [conclusion.isSuccess, caseId, mutate])

  if (conclusion.isPending) return <p className="text-muted">{t.conclusionLoading}</p>
  if (conclusion.isError) return <ErrorState onRetry={() => void conclusion.refetch()} />

  return (
    <div className="space-y-2">
      <h3 className="text-base font-semibold">{t.conclusionHeading}</h3>
      <p className="whitespace-pre-wrap rounded border border-hairline bg-card p-3">
        {conclusion.data.text}
      </p>
      <p className="text-sm text-muted">
        {t.signedBy(conclusion.data.signed_by.display, formatDateTime(conclusion.data.signed_at))}
      </p>
      <p aria-live="polite" className="text-sm text-muted">
        {opened.isSuccess && t.openedRecorded}
        {opened.isError && (
          <span role="alert">
            {t.openedFailed(problemTitle(opened.error))}{' '}
            <button type="button" className="underline" onClick={() => opened.mutate(caseId)}>
              {t.openedRetry}
            </button>
          </span>
        )}
      </p>
    </div>
  )
}

function MdtResult({ c }: { c: CaseSummary }) {
  const [open, setOpen] = useState(false)
  const panel = `conclusion-${c.id}`
  return (
    <div className="space-y-3 rounded-lg border border-ai/30 bg-ai-bg/50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-medium">{c.patientName}</p>
          <p className="text-sm text-muted">{t.mdtText}</p>
        </div>
        <Button
          variant={open ? 'secondary' : 'primary'}
          aria-expanded={open}
          aria-controls={panel}
          aria-label={open ? undefined : t.openConclusionAria(c.patientName)}
          onClick={() => setOpen((o) => !o)}
        >
          {open ? t.closeConclusion : t.openConclusion}
        </Button>
      </div>
      <div id={panel}>{open && <Conclusion caseId={c.id} />}</div>
    </div>
  )
}

export function Gp() {
  const q = useGpCases()

  if (q.isPending) return <LoadingBlock lines={5} />
  if (q.isError) return <ErrorState onRetry={() => void q.refetch()} />

  const toOpen = q.data.filter((c) => c.state === 'zpetna_vazba_odeslana')

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl">{t.title}</h1>
        <Button asChild variant={toOpen.length ? 'secondary' : 'primary'}>
          <Link to="/referral/new">{t.newReferral}</Link>
        </Button>
      </div>

      {q.data.length === 0 && (
        <EmptyState
          title={t.empty}
          hint={t.emptyHint}
          action={
            <Button asChild variant="primary">
              <Link to="/referral/new">{t.newReferral}</Link>
            </Button>
          }
        />
      )}

      {toOpen.length > 0 && (
        <section aria-labelledby="mdt-h" className="space-y-2">
          <h2 id="mdt-h" className="text-xl">
            {t.mdtTitle}
          </h2>
          {toOpen.map((c) => (
            <MdtResult key={c.id} c={c} />
          ))}
        </section>
      )}

      {q.data.length > 0 && (
        <table className="w-full border-collapse overflow-hidden rounded-lg border border-hairline bg-card">
          <thead className="border-b border-hairline">
            <tr>
              {Object.values(t.cols).map((c) => (
                <th
                  key={c}
                  className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted"
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {q.data.map((c) => (
              <tr key={c.id} className="border-b border-hairline last:border-0">
                <td className="px-3 py-3 align-top">
                  <Link to={`/cases/${c.id}`} className="font-medium hover:underline">
                    {c.patientName}
                  </Link>
                  {c.diagnosis && <p className="text-xs text-muted">{c.diagnosis}</p>}
                </td>
                <td className="px-3 py-3 align-top">
                  <CaseStateBadge state={c.state} />
                  {c.subStatus && <p className="mt-1 text-xs text-muted">{c.subStatus}</p>}
                </td>
                <td className="px-3 py-3 align-top">
                  <div className="flex flex-wrap gap-2">
                    <CountBadge kind="missing" count={c.counts.missing} />
                    <CountBadge kind="conflict" count={c.counts.conflict} />
                    <CountBadge kind="stale" count={c.counts.stale} />
                    {c.counts.missing === 0 && c.counts.conflict === 0 && c.counts.stale === 0 && (
                      <span className="text-sm text-muted">{t.nothingMissing}</span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-3 align-top">
                  <BatonHolder baton={c.baton} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
