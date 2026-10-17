// One rendering of a T1–T3 proxy for the case header and the reviewer screen: days only when the API measured them.
import { cases as t } from '@/i18n/cs/cases'
import type { TreatmentInterval } from '@/lib/domain'

export function intervalText(i: TreatmentInterval | undefined): string {
  if (!i) return t.header.unknown
  if (i.status === 'measured') return i.days === null ? t.header.unknown : t.header.days(i.days)
  return t.header.intervalStatus[i.status]
}
