import { BatonHolder } from '@/components/BatonHolder'
import { CaseStateBadge } from '@/components/CaseStateBadge'
import { StatusPill } from '@/components/StatusPill'
import { cases as t } from '@/i18n/cs/cases'
import { formatDate } from '@/lib/date'
import type { CaseDetail, TreatmentInterval } from '@/lib/domain'
import { intervalText } from '../intervals'
import { CaseAction } from './CaseAction'

const dash = '—'

function Counter({ kind, n }: { kind: 'missing' | 'conflict' | 'stale'; n: number | null }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="font-serif text-3xl font-semibold leading-none"
        aria-label={n === null ? 'počet zatím nespočítán' : `počet: ${n}`}
      >
        {n ?? dash}
      </span>
      <StatusPill kind={kind} />
    </div>
  )
}

function Clock({ label, value }: { label: string; value: TreatmentInterval | undefined }) {
  return (
    <div className="rounded border border-hairline px-3 py-1.5">
      <p className="font-mono text-sm font-semibold">{intervalText(value)}</p>
      <p className="text-xs text-muted">{label}</p>
    </div>
  )
}

/** Only what is known: a field the backend does not send is left out, not shown as "—". */
const joinKnown = (parts: Array<string | null | undefined>) => parts.filter(Boolean).join(' · ')

/** Readable in 3 seconds: state, baton + deadline, missing/conflict/stale counts. */
export function CaseHeader({ c }: { c: CaseDetail }) {
  const identity = joinKnown([
    formatDate(c.birthDate),
    c.birthNumber && `${t.header.birthNumber} ${c.birthNumber}`,
    c.diagnosis,
  ])
  const labelled = (label: string, value: string | null | undefined) =>
    value && `${label}: ${value}`
  const parties = joinKnown([
    labelled(t.header.insurer, c.insurer ?? c.insurerCode),
    labelled(t.header.koc, c.koc),
    labelled(t.header.gp, c.gp),
  ])
  return (
    <section aria-label={c.patientName} className="rounded-lg border border-hairline bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-baseline gap-x-4">
          <h1 className="text-3xl">{c.patientName}</h1>
          <p className="text-sm text-muted">{identity}</p>
        </div>
        <CaseAction c={c} />
      </div>
      <div className="mt-4 grid gap-6 md:grid-cols-[1.1fr_1.3fr_1fr]">
        <CaseStateBadge state={c.state} variant="stepper" />
        <BatonHolder baton={c.baton} size="lg" />
        <div role="group" aria-label={t.header.counters} className="space-y-1.5">
          <Counter kind="missing" n={c.counts.missing} />
          <Counter kind="conflict" n={c.counts.conflict} />
          <Counter kind="stale" n={c.counts.stale} />
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-end justify-between gap-3 border-t border-hairline pt-3">
        {parties && <p className="text-xs text-muted">{parties}</p>}
        <div className="ml-auto space-y-1">
          <div role="group" aria-label={t.header.clocks} className="flex flex-wrap gap-2">
            <Clock label={t.header.t1} value={c.intervals?.t1} />
            <Clock label={t.header.t2} value={c.intervals?.t2} />
            <Clock label={t.header.t3} value={c.intervals?.t3} />
          </div>
          <p className="text-right text-xs text-muted">{t.header.clocksHint}</p>
        </div>
      </div>
    </section>
  )
}
