import { Link } from 'react-router-dom'
import { BatonHolder } from '@/components/BatonHolder'
import { CaseStateBadge } from '@/components/CaseStateBadge'
import { CountBadge } from '@/components/CountBadge'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { gp as t } from '@/i18n/cs/gp'
import { useAcknowledge, useGpCases } from './api'

export function Gp() {
  const q = useGpCases()
  const ack = useAcknowledge()

  if (q.isPending) return <LoadingBlock lines={5} />
  if (q.isError) return <ErrorState onRetry={() => void q.refetch()} />

  const toAck = q.data.filter((c) => c.state === 'zpetna_vazba_odeslana')
  const primaryId = toAck[0]?.id

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl">{t.title}</h1>
        <Button asChild variant={toAck.length ? 'secondary' : 'primary'}>
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

      {toAck.length > 0 && (
        <section aria-labelledby="mdt-h" className="space-y-2">
          <h2 id="mdt-h" className="text-xl">
            {t.mdtTitle}
          </h2>
          {toAck.map((c) => (
            <div key={c.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-ai/30 bg-ai-bg/50 p-4">
              <div>
                <p className="font-medium">{c.patientName}</p>
                <p className="text-sm text-muted">{t.mdtText}</p>
              </div>
              <Button
                variant={c.id === primaryId ? 'primary' : 'secondary'}
                disabled={ack.isPending}
                onClick={() => ack.mutate(c.id)}
                aria-label={t.acknowledgeAria(c.patientName)}
              >
                {t.acknowledge}
              </Button>
            </div>
          ))}
        </section>
      )}

      {q.data.length > 0 && (
        <table className="w-full border-collapse overflow-hidden rounded-lg border border-hairline bg-card">
          <thead className="border-b border-hairline">
            <tr>
              {Object.values(t.cols).map((c) => (
                <th key={c} className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
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
                  <p className="text-xs text-muted">{c.diagnosis}</p>
                </td>
                <td className="px-3 py-3 align-top">
                  <CaseStateBadge state={c.state} />
                  <p className="mt-1 text-xs text-muted">{c.subStatus}</p>
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
