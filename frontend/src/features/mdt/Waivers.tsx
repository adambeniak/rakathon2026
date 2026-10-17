import { mdt as t } from '@/i18n/cs/mdt'
import { formatDateTime } from '@/lib/date'
import type { ReadinessWaiverInfo } from '@/lib/domain'

/** The readiness items a KOC physician waived, as the case API returns them (who, when, why). Hidden when none. */
export function Waivers({ waivers }: { waivers: ReadinessWaiverInfo[] }) {
  if (waivers.length === 0) return null
  return (
    <section
      aria-labelledby="waivers-h"
      className="space-y-2 rounded-lg border border-hairline bg-card p-4"
    >
      <h3 id="waivers-h" className="text-xl">
        {t.waivers.title}
      </h3>
      <p className="text-sm text-muted">{t.waivers.hint}</p>
      <ul className="space-y-2">
        {waivers.map((w) => (
          <li key={w.item} className="text-sm">
            <p className="font-medium">{t.ready.items[w.item] ?? w.item}</p>
            <p>{t.waivers.entry(w.by ?? t.waivers.unnamed, formatDateTime(w.at), w.reason)}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}
