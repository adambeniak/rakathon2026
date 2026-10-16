import { BatonHolder } from '@/components/BatonHolder'
import { CaseStateBadge } from '@/components/CaseStateBadge'
import { StatusPill } from '@/components/StatusPill'
import { cases as t } from '@/i18n/cs/cases'
import { formatDate } from '@/lib/date'
import type { CaseDetail } from '@/lib/domain'

const dash = '—'

function Counter({ kind, n }: { kind: 'missing' | 'conflict' | 'stale'; n: number | null }) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-serif text-3xl font-semibold leading-none" aria-label={n === null ? 'počet zatím nespočítán' : `počet: ${n}`}>
        {n ?? dash}
      </span>
      <StatusPill kind={kind} />
    </div>
  )
}

function Clock({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded border border-hairline px-3 py-1.5">
      <p className="font-mono text-sm font-semibold">{value === null ? t.header.pending : t.header.days(value)}</p>
      <p className="text-xs text-muted">{label}</p>
    </div>
  )
}

/** Readable in 3 seconds: state, baton + deadline, missing/conflict/stale counts. */
export function CaseHeader({ c }: { c: CaseDetail }) {
  return (
    <section aria-label={c.patientName} className="rounded-lg border border-hairline bg-card p-5">
      <div className="flex flex-wrap items-baseline gap-x-4">
        <h1 className="text-3xl">{c.patientName}</h1>
        <p className="text-sm text-muted">
          {formatDate(c.birthDate)} · {t.header.birthNumber} {c.birthNumber ?? dash} · {c.diagnosis ?? dash}
        </p>
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
        <p className="text-xs text-muted">
          {t.header.insurer}: {c.insurer ?? c.insurerCode ?? dash} · {t.header.koc}: {c.koc ?? dash} · {t.header.gp}: {c.gp ?? dash}
        </p>
        <div role="group" aria-label={t.header.clocks} className="flex flex-wrap gap-2">
          <Clock label={t.header.t1} value={c.t?.t1 ?? null} />
          <Clock label={t.header.t2} value={c.t?.t2 ?? null} />
          <Clock label={t.header.t3} value={c.t?.t3 ?? null} />
        </div>
      </div>
    </section>
  )
}
