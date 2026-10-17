import { FlaskConical } from 'lucide-react'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { insurer as t } from '@/i18n/cs/insurer'
import { formatDate } from '@/lib/date'
import { useInsurerAnalytics, type CoordinatorRow, type InsurerAnalytics } from './api'
import { money, num, percent, share } from './format'
import { HospitalsTable } from './Hospitals'
import { JourneysList } from './Journeys'

const th =
  'px-3 py-2 text-left align-bottom text-xs font-semibold uppercase tracking-wide text-muted'
const td = 'px-3 py-3 align-top'

function Notice({ disclaimer }: { disclaimer?: string }) {
  // The API disclaimer starts with the same sentence as the notice: show only what it adds.
  const rest = disclaimer?.startsWith(t.notice) ? disclaimer.slice(t.notice.length).trim() : disclaimer
  return (
    <div
      role="note"
      className="flex items-start gap-2 rounded-lg border border-accent/40 bg-accent-soft p-3 text-ink"
    >
      <FlaskConical aria-hidden className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
      <div className="space-y-1">
        <p className="font-medium">{t.notice}</p>
        {rest && <p className="text-sm">{rest}</p>}
      </div>
    </div>
  )
}

function KeyFacts({ data }: { data: InsurerAnalytics }) {
  const m = data.summary.median_days
  const days = (v: number | null) => (v === null ? t.notRecorded : t.days(v))
  const facts = [
    [t.facts.cases, t.facts.casesValue(data.summary.cases, data.summary.simulated_cases)],
    [t.facts.contactToMdt, days(m.contact_to_mdt)],
    [t.facts.ctWait, days(m.ct_order_to_ct)],
    [t.facts.biopsyWait, days(m.biopsy_order_to_biopsy)],
  ] as const
  return (
    <section aria-labelledby="insurer-facts">
      <h2 id="insurer-facts" className="sr-only">
        {t.facts.heading}
      </h2>
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {facts.map(([label, value]) => (
          <div key={label} className="rounded-lg border border-hairline bg-card p-3">
            <dt className="text-sm text-muted">{label}</dt>
            <dd className="mt-1 font-serif text-xl">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function Formula({ data }: { data: InsurerAnalytics }) {
  const a = data.assumptions
  return (
    <details className="rounded-lg border border-hairline bg-card p-3">
      <summary className="cursor-pointer font-medium">{t.formula.summary}</summary>
      <div className="mt-3 space-y-2 text-sm">
        <p>{a.formula}</p>
        <p>
          {t.formula.weights(
            share(a.weights.speed),
            share(a.weights.cost),
            share(a.weights.target_share),
          )}
        </p>
        <p>
          {t.formula.targets(
            a.targets.ct_order_to_ct_max_days,
            a.targets.biopsy_order_to_biopsy_max_days,
          )}{' '}
          <span className="text-muted">({a.targets.note})</span>
        </p>
        <p>
          {t.formula.capacity(
            a.capacity.minutes_per_week,
            formatDate(a.capacity.period_start),
            formatDate(a.capacity.period_end),
            num(a.capacity.weeks),
          )}{' '}
          <span className="text-muted">({a.capacity.note})</span>
        </p>
        <div className="overflow-x-auto">
          <table className="min-w-[20rem] border-collapse">
            <caption className="py-1 text-left font-medium">
              {t.formula.priceList}{' '}
              <span className="font-normal text-muted">– {a.price_list_note}</span>
            </caption>
            <thead>
              <tr>
                <th scope="col" className={th}>
                  {t.formula.priceCols.item}
                </th>
                <th scope="col" className={th}>
                  {t.formula.priceCols.price}
                </th>
              </tr>
            </thead>
            <tbody>
              {a.price_list.map((p) => (
                <tr key={p.code} className="border-t border-hairline">
                  <td className="px-3 py-1">{p.label}</td>
                  <td className="whitespace-nowrap px-3 py-1 text-right font-mono">
                    {money(p.price_czk)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </details>
  )
}

function CoordinatorsTable({ rows }: { rows: CoordinatorRow[] }) {
  const c = t.coordinators.cols
  return (
    <div className="overflow-x-auto rounded-lg border border-hairline bg-card">
      <table className="w-full min-w-[44rem] border-collapse">
        <caption className="px-3 pt-3 text-left text-sm text-muted">
          <span className="sticky left-3 block max-w-[calc(100vw-4rem)]">{t.coordinators.caption}</span>
        </caption>
        <thead className="border-b border-hairline">
          <tr>
            {[c.name, c.hospital, c.cases, c.minutes, c.accepted, c.utilisation].map((label) => (
              <th key={label} scope="col" className={th}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-hairline last:border-0">
              <th scope="row" className={`${td} text-left font-medium`}>
                {r.display}
              </th>
              <td className={td}>{r.hospital_name}</td>
              <td className={`${td} font-mono text-sm`}>{r.cases}</td>
              <td className={`${td} font-mono text-sm`}>{num(r.median_minutes_per_patient)}</td>
              <td className={`${td} font-mono text-sm`}>
                {num(r.median_days_contact_to_accepted)}
              </td>
              <td className={`${td} whitespace-nowrap font-mono text-sm`}>
                {percent(r.utilisation_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Insurer() {
  const q = useInsurerAnalytics()
  return (
    <div className="min-w-0 space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl">{t.title}</h1>
        <p className="text-muted">{t.lead}</p>
      </header>
      <Notice disclaimer={q.data?.disclaimer} />
      {q.isPending ? (
        <LoadingBlock lines={6} />
      ) : q.isError ? (
        q.error.status === 403 ? (
          <EmptyState title={t.forbidden} hint={t.lead} />
        ) : (
          <ErrorState onRetry={() => void q.refetch()} />
        )
      ) : q.data.journeys.length === 0 ? (
        <EmptyState title={t.empty} hint={t.emptyHint} />
      ) : (
        <>
          <p className="text-sm text-muted">{t.asOf(formatDate(q.data.as_of))}</p>
          <KeyFacts data={q.data} />
          <section aria-labelledby="insurer-hospitals" className="space-y-3">
            <h2 id="insurer-hospitals" className="text-2xl">
              {t.hospitals.heading}
            </h2>
            <HospitalsTable rows={q.data.hospitals} />
            <Formula data={q.data} />
          </section>
          <section aria-labelledby="insurer-coordinators" className="space-y-3">
            <h2 id="insurer-coordinators" className="text-2xl">
              {t.coordinators.heading}
            </h2>
            <CoordinatorsTable rows={q.data.coordinators} />
          </section>
          <section aria-labelledby="insurer-journeys" className="space-y-3">
            <h2 id="insurer-journeys" className="text-2xl">
              {t.journeys.heading}
            </h2>
            <p className="text-sm text-muted">{t.journeys.hint}</p>
            <JourneysList rows={q.data.journeys} />
          </section>
        </>
      )}
    </div>
  )
}
