// Display formatting only (Czech locale). Every value is computed by the API; nothing is derived here.
import { insurer as t } from '@/i18n/cs/insurer'

const decimal = new Intl.NumberFormat('cs-CZ', { maximumFractionDigits: 1 })
const czk = new Intl.NumberFormat('cs-CZ', {
  style: 'currency',
  currency: 'CZK',
  maximumFractionDigits: 0,
})

/** `2,5` or `—` for a value the API could not measure. */
export const num = (value: number | null): string =>
  value === null ? t.dash : decimal.format(value)

/** `12 345 Kč` */
export const money = (value: number | null): string => (value === null ? t.dash : czk.format(value))

/** `32,7 %` */
export const percent = (value: number | null): string =>
  value === null ? t.dash : `${decimal.format(value)} %`

/** `50 %` from a 0–1 weight */
export const share = (value: number): string => `${decimal.format(value * 100)} %`
