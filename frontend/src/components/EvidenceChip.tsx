import * as Popover from '@radix-ui/react-popover'
import { FileText } from 'lucide-react'
import { common } from '@/i18n/cs/common'
import { formatDate } from '@/lib/date'
import type { DocumentInfo } from '@/lib/domain'

/** Every AI-derived value is rendered with its source: document, date and verbatim quote. */
export function EvidenceChip({ docId, quote, doc }: { docId: string; quote?: string; doc?: DocumentInfo }) {
  const info = doc
  const number = docId.slice(0, 2)
  const title = info?.title ?? docId
  return (
    <Popover.Root>
      <Popover.Trigger
        className="inline-flex items-center gap-1 rounded border border-hairline bg-card px-2 py-0.5 text-xs hover:bg-accent-soft"
        aria-label={`${common.evidence.source}: ${title}${info ? `, ${formatDate(info.authored)}` : ''}`}
      >
        <FileText aria-hidden className="h-3 w-3 text-accent" />
        <span className="font-mono">{number}</span>
        <span className="max-w-[16ch] truncate">{title}</span>
        {info && <span className="text-muted">{formatDate(info.authored)}</span>}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="start"
          sideOffset={6}
          className="z-50 w-80 rounded-lg border border-hairline bg-card p-3 text-sm shadow-lg"
        >
          <p className="font-semibold">{title}</p>
          {info && (
            <p className="text-xs text-muted">
              {info.place} · {common.evidence.authored} {formatDate(info.authored)} · {common.evidence.received}{' '}
              {formatDate(info.received)}
            </p>
          )}
          <p className="mt-2 text-xs font-medium text-muted">{common.evidence.quote}</p>
          {quote ? (
            <blockquote className="mt-1 border-l-2 border-accent pl-2 font-mono text-xs">{quote}</blockquote>
          ) : (
            <p className="mt-1 text-xs text-muted">{common.evidence.noQuote}</p>
          )}
          <Popover.Close className="mt-2 text-xs text-accent underline">{common.evidence.close}</Popover.Close>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
