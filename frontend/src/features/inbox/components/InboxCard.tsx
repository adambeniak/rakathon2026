import { Link } from 'react-router-dom'
import { BatonHolder } from '@/components/BatonHolder'
import { CaseStateBadge } from '@/components/CaseStateBadge'
import { CountBadge } from '@/components/CountBadge'
import { Button } from '@/components/ui/button'
import { inbox as t } from '@/i18n/cs/inbox'
import { formatDate } from '@/lib/date'
import type { CaseSummary } from '@/lib/domain'

export function InboxCard({
  c,
  onClaim,
  claiming,
}: {
  c: CaseSummary
  onClaim?: (id: string) => void
  claiming?: boolean
}) {
  return (
    <article className="space-y-3 rounded-lg border border-hairline bg-card p-4" aria-label={c.patientName}>
      <header className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-base">
            <Link to={`/cases/${c.id}`} className="hover:underline">
              {c.patientName}
            </Link>
          </h3>
          <p className="text-xs text-muted">
            {c.diagnosis} · {t.referredAt} {formatDate(c.referredAt)} · {t.gp} {c.gp}
          </p>
        </div>
        {c.urgent && <span className="rounded bg-missing-bg px-1.5 py-0.5 text-xs font-semibold text-missing">{t.urgent}</span>}
      </header>
      <CaseStateBadge state={c.state} />
      <p className="text-sm">{c.subStatus}</p>
      <BatonHolder baton={c.baton} />
      <div className="flex flex-wrap gap-2">
        <CountBadge kind="missing" count={c.counts.missing} />
        <CountBadge kind="conflict" count={c.counts.conflict} />
        <CountBadge kind="stale" count={c.counts.stale} />
      </div>
      {onClaim && (
        <Button variant="primary" disabled={claiming} onClick={() => onClaim(c.id)} aria-label={t.claimAria(c.patientName)}>
          {t.claim}
        </Button>
      )}
    </article>
  )
}
