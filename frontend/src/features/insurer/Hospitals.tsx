import { Coins, Zap, type LucideIcon } from 'lucide-react'
import { insurer as t } from '@/i18n/cs/insurer'
import type { HospitalRow } from './api'
import { money, num, percent } from './format'

const BADGE_ICON: Record<HospitalRow['badges'][number], LucideIcon> = {
  fastest: Zap,
  lowest_cost: Coins,
}

const th =
  'px-3 py-2 text-left align-bottom text-xs font-semibold uppercase tracking-wide text-muted'
const td = 'px-3 py-3 align-top'

export function Badge({ kind }: { kind: HospitalRow['badges'][number] }) {
  const Icon = BADGE_ICON[kind]
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-accent">
      <Icon aria-hidden className="h-3.5 w-3.5" />
      {t.hospitals.badges[kind]}
    </span>
  )
}

function IndicatorCell({ value }: { value: number | null }) {
  return (
    <div className="flex min-w-32 items-center gap-2">
      <span className="w-10 text-right font-mono text-sm font-semibold">{num(value)}</span>
      <span aria-hidden className="h-2 flex-1 overflow-hidden rounded-full bg-hairline">
        <span className="block h-full rounded-full bg-accent" style={{ width: `${value ?? 0}%` }} />
      </span>
    </div>
  )
}

export function HospitalsTable({ rows }: { rows: HospitalRow[] }) {
  const c = t.hospitals.cols
  return (
    <div className="overflow-x-auto rounded-lg border border-hairline bg-card">
      <table className="w-full min-w-[60rem] border-collapse">
        <caption className="px-3 pt-3 text-left text-sm text-muted">
          <span className="sticky left-3 block max-w-[calc(100vw-4rem)]">{t.hospitals.caption}</span>
        </caption>
        <thead className="border-b border-hairline">
          <tr>
            <th scope="col" className={th}>
              {c.rank}
            </th>
            <th scope="col" className={th}>
              {c.hospital}
            </th>
            <th scope="col" className={th}>
              {c.cases}
            </th>
            <th scope="col" className={th}>
              {c.ct}
            </th>
            <th scope="col" className={th}>
              {c.biopsy}
            </th>
            <th scope="col" className={th}>
              {c.mdt}
            </th>
            <th scope="col" className={th}>
              {c.treatment}
            </th>
            <th scope="col" className={th}>
              {c.cost}
            </th>
            <th scope="col" className={th}>
              {c.minutes}
            </th>
            <th scope="col" className={th}>
              {c.utilisation}
            </th>
            <th scope="col" className={th}>
              {c.indicator}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((h) => (
            <tr key={h.id} className="border-b border-hairline last:border-0">
              <td className={`${td} font-mono text-sm`}>{h.indicator_rank ?? t.dash}.</td>
              <th scope="row" className={`${td} text-left font-medium`}>
                <span className="block">{h.name}</span>
                {h.badges.length > 0 && (
                  <span className="mt-1 flex flex-wrap gap-1">
                    {h.badges.map((b) => (
                      <Badge key={b} kind={b} />
                    ))}
                  </span>
                )}
              </th>
              <td className={`${td} font-mono text-sm`}>{h.cases}</td>
              <td className={`${td} font-mono text-sm`}>{num(h.median_days.ct_order_to_ct)}</td>
              <td className={`${td} font-mono text-sm`}>
                {num(h.median_days.biopsy_order_to_biopsy)}
              </td>
              <td className={`${td} font-mono text-sm`}>{num(h.median_days.contact_to_mdt)}</td>
              <td className={`${td} font-mono text-sm`}>{num(h.median_days.mdt_to_treatment)}</td>
              <td className={`${td} whitespace-nowrap font-mono text-sm`}>
                {money(h.median_cost_czk)}
              </td>
              <td className={`${td} font-mono text-sm`}>{num(h.median_coordinator_minutes)}</td>
              <td className={`${td} whitespace-nowrap font-mono text-sm`}>
                {percent(h.utilisation_pct)}
              </td>
              <td className={td}>
                <IndicatorCell value={h.indicator} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
