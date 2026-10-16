import { differenceInCalendarDays, format, parseISO } from 'date-fns'
import { cs } from 'date-fns/locale'

const TZ = 'Europe/Prague'

/** Calendar date (YYYY-MM-DD or ISO timestamp) as Prague-local date. */
function toPragueDate(iso: string): Date {
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return parseISO(iso)
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(new Date(iso))
  return parseISO(parts)
}

/** `21. 10. 2026` */
export function formatDate(iso: string): string {
  return format(toPragueDate(iso), 'd. M. yyyy', { locale: cs })
}

/** `21. 10. 2026 8:00` in Europe/Prague */
export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  const time = new Intl.DateTimeFormat('cs-CZ', {
    timeZone: TZ,
    hour: 'numeric',
    minute: '2-digit',
  }).format(d)
  return `${formatDate(iso)} ${time}`
}

/** Whole calendar days from `today` to `due` (negative = overdue). */
export function daysUntil(dueIso: string, todayIso: string): number {
  return differenceInCalendarDays(toPragueDate(dueIso), toPragueDate(todayIso))
}

/** `za 3 dny`, `dnes`, `po termínu 2 dny` */
export function formatRemaining(days: number): string {
  if (days === 0) return 'dnes'
  if (days === 1) return 'zítra'
  if (days > 1) return `za ${days} ${days < 5 ? 'dny' : 'dní'}`
  const n = Math.abs(days)
  return `po termínu ${n} ${n === 1 ? 'den' : n < 5 ? 'dny' : 'dní'}`
}

/** True when `iso` is at or before `asOfIso` (both timestamps). */
export function isOnOrBefore(iso: string, asOfIso: string): boolean {
  return new Date(iso).getTime() <= new Date(asOfIso).getTime()
}

/** `2026-10-21T08:00` (Prague wall-clock) → ISO timestamp with the right Prague offset. */
export function pragueLocalToIso(local: string): string {
  const withSeconds = local.length === 16 ? `${local}:00` : local
  for (const offset of ['+02:00', '+01:00']) {
    const d = new Date(`${withSeconds}${offset}`)
    const hour = new Intl.DateTimeFormat('cs-CZ', { timeZone: TZ, hour: '2-digit', hourCycle: 'h23' }).format(d)
    if (Number(hour) === Number(withSeconds.slice(11, 13))) return `${withSeconds}${offset}`
  }
  return `${withSeconds}+01:00`
}

/** ISO timestamp → `YYYY-MM-DDTHH:mm` Prague wall-clock for <input type="datetime-local">. */
export function isoToPragueLocal(iso: string): string {
  const p = new Intl.DateTimeFormat('sv-SE', {
    timeZone: TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(new Date(iso))
  return p.replace(' ', 'T')
}
