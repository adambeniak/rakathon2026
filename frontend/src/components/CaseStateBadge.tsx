import { Check } from 'lucide-react'
import { common } from '@/i18n/cs/common'
import { CASE_STATES, type CaseState } from '@/lib/domain'
import { cn } from '@/lib/cn'

/** Chip for lists; stepper for the case header. Teal ramp, deliberately not the status colours. */
export function CaseStateBadge({ state, variant = 'chip' }: { state: CaseState; variant?: 'chip' | 'stepper' }) {
  const label = common.caseStates[state]
  const idx = CASE_STATES.indexOf(state)
  if (variant === 'chip') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded bg-accent-soft px-2 py-0.5 text-xs font-semibold text-accent">
        <span className="font-mono text-[11px]" aria-hidden>
          {idx + 1}/8
        </span>
        {label}
      </span>
    )
  }
  return (
    <div>
      <p className="font-serif text-2xl text-accent">
        <span className="sr-only">Stav případu: </span>
        {label}
      </p>
      <ol aria-label="Průběh případu" className="mt-2 flex gap-1">
        {CASE_STATES.map((s, i) => (
          <li
            key={s}
            title={common.caseStates[s]}
            aria-current={i === idx ? 'step' : undefined}
            className={cn(
              'flex h-5 min-w-5 items-center justify-center rounded-sm text-[10px] font-semibold',
              i < idx && 'bg-accent text-white',
              i === idx && 'bg-accent text-white ring-2 ring-accent ring-offset-2',
              i > idx && 'bg-hairline text-muted',
            )}
          >
            {i < idx ? <Check aria-hidden className="h-3 w-3" /> : i + 1}
            <span className="sr-only">{`${common.caseStates[s]}${i < idx ? ' – hotovo' : i === idx ? ' – aktuální' : ''}`}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
