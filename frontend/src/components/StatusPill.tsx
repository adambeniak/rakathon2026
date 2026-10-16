import { BadgeCheck, CircleAlert, CircleCheck, CircleDashed, Clock, HelpCircle, Sparkles, TriangleAlert, type LucideIcon } from 'lucide-react'
import { common } from '@/i18n/cs/common'
import type { HandoverStatus } from '@/lib/domain'
import { cn } from '@/lib/cn'

export type PillKind = 'missing' | 'conflict' | 'stale' | 'verified' | 'ai' | 'complete' | 'partial' | 'clarify' | 'excluded'

const MAP: Record<PillKind, { Icon: LucideIcon; label: string; cls: string }> = {
  missing: { Icon: CircleAlert, label: common.status.missing, cls: 'bg-missing-bg text-missing' },
  conflict: { Icon: TriangleAlert, label: common.status.conflict, cls: 'bg-conflict-bg text-conflict' },
  stale: { Icon: Clock, label: common.status.stale, cls: 'bg-stale-bg text-stale' },
  verified: { Icon: BadgeCheck, label: common.status.verified, cls: 'bg-verified-bg text-verified' },
  ai: { Icon: Sparkles, label: common.status.ai, cls: 'bg-ai-bg text-ai' },
  complete: { Icon: CircleCheck, label: common.status.complete, cls: 'border border-hairline text-ink' },
  partial: { Icon: CircleDashed, label: common.status.partial, cls: 'border border-hairline text-ink' },
  clarify: { Icon: HelpCircle, label: common.status.clarify, cls: 'bg-conflict-bg text-conflict' },
  excluded: { Icon: Clock, label: common.status.excluded, cls: 'bg-stale-bg text-stale' },
}

/** The fixed status semantics: always icon + text, never colour alone. */
export function StatusPill({ kind, className }: { kind: PillKind; className?: string }) {
  const { Icon, label, cls } = MAP[kind]
  return (
    <span className={cn('inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium', cls, className)}>
      <Icon aria-hidden className="h-3.5 w-3.5" />
      {label}
    </span>
  )
}

/** Pills for a handover section: AI draft until confirmed, plus data-quality flags. */
export function pillForHandover(status: HandoverStatus, confirmed: boolean): PillKind[] {
  const flags: PillKind[] =
    status === 'missing'
      ? ['missing']
      : status === 'stale'
        ? ['stale']
        : status === 'complete_with_conflict'
          ? ['conflict']
          : status === 'needs_clarification'
            ? ['clarify']
            : status === 'partial'
              ? ['partial', 'missing']
              : []
  if (confirmed) return ['verified', ...flags]
  return status === 'missing' ? flags : ['ai', ...flags]
}
