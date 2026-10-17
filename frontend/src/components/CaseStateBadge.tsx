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
      <span className="inline-flex items-center gap-2 whitespace-nowrap rounded-sm bg-accent-soft py-0.5 pl-2 pr-2.5 text-xs font-semibold text-accent">
        <span className="font-mono text-xs font-medium" aria-hidden>
          {idx + 1}/8
        </span>
        {label}
      </span>
    )
  }
  return (
    <div>
      <p className="text-2xl font-semibold text-accent">
        <span className="sr-only">Stav případu: </span>
        {label}
      </p>
      <ol aria-label="Průběh případu" className="mt-3 flex flex-wrap gap-1.5">
        {CASE_STATES.map((s, i) => (
          <li
            key={s}
            title={common.caseStates[s]}
            aria-current={i === idx ? 'step' : undefined}
            className={cn(
              'flex h-7 min-w-7 items-center justify-center rounded-full font-mono text-xs font-semibold',
              i < idx && 'bg-accent text-accent-on',
              i === idx && 'bg-accent text-accent-on ring-4 ring-accent-soft',
              i > idx && 'border-[1.5px] border-line-strong bg-card text-muted',
            )}
          >
            {i < idx ? <Check aria-hidden className="h-4 w-4" strokeWidth={2.5} /> : i + 1}
            <span className="sr-only">{`${common.caseStates[s]}${i < idx ? ' – hotovo' : i === idx ? ' – aktuální' : ''}`}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
