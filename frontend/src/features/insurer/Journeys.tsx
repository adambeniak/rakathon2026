import { ArrowRight } from 'lucide-react'
import { insurer as t } from '@/i18n/cs/insurer'
import { formatDate } from '@/lib/date'
import type { JourneyRow } from './api'
import { money } from './format'

function Milestones({ journey }: { journey: JourneyRow }) {
  const labels = t.journeys.milestones
  return (
    <ol className="flex flex-wrap items-stretch gap-x-1 gap-y-2">
      {journey.milestones.map((m, i) => {
        const previous = i > 0 ? journey.milestones[i - 1] : undefined
        return (
          <li key={m.key} className="flex items-center gap-1">
            {previous && (
              <span className="flex items-center gap-1 text-xs text-muted">
                <ArrowRight aria-hidden className="h-3.5 w-3.5" />
                {m.days_since_previous !== null && (
                  <span
                    className="rounded-full bg-accent-soft px-2 py-0.5 font-mono text-accent"
                    aria-label={t.plusDaysAria(m.days_since_previous, labels[previous.key])}
                  >
                    {t.plusDays(m.days_since_previous)}
                  </span>
                )}
              </span>
            )}
            <span className="rounded border border-hairline px-2 py-1">
              <span className="block text-xs text-muted">{labels[m.key]}</span>
              {m.date ? (
                <span className="block font-mono text-sm">{formatDate(m.date)}</span>
              ) : (
                <span className="block text-sm italic text-muted">{t.notRecorded}</span>
              )}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function JourneyCards({ rows }: { rows: JourneyRow[] }) {
  return (
    <ul className="space-y-3">
      {rows.map((j) => (
        <li key={j.code} className="rounded-lg border border-hairline bg-card p-3">
          <article aria-labelledby={`journey-${j.code}`} className="space-y-2">
            <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h3 id={`journey-${j.code}`} className="font-mono text-sm font-semibold">
                {j.code}
              </h3>
              <span
                className={
                  j.simulated
                    ? 'rounded-full border border-hairline px-2 py-0.5 text-xs text-muted'
                    : 'rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent'
                }
              >
                {j.simulated ? t.journeys.simulated : t.journeys.demo}
              </span>
              <span className="text-sm">{j.hospital_name}</span>
              <span className="text-sm text-muted">
                {t.journeys.coordinator(j.coordinator_display)}
              </span>
              <span className="text-sm text-muted">{t.journeys.cost(money(j.cost_czk))}</span>
            </header>
            <Milestones journey={j} />
          </article>
        </li>
      ))}
    </ul>
  )
}

/** The demo case(s) first and open; the simulated journeys behind one disclosure so the page stays short. */
export function JourneysList({ rows }: { rows: JourneyRow[] }) {
  const real = rows.filter((j) => !j.simulated)
  const simulated = rows.filter((j) => j.simulated)
  return (
    <div className="space-y-3">
      {real.length > 0 && <JourneyCards rows={real} />}
      {simulated.length > 0 && (
        <details className="space-y-3">
          <summary className="cursor-pointer font-medium">{t.journeys.showSimulated(simulated.length)}</summary>
          <div className="mt-3">
            <JourneyCards rows={simulated} />
          </div>
        </details>
      )}
    </div>
  )
}
