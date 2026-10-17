import * as Dialog from '@radix-ui/react-dialog'
import * as Popover from '@radix-ui/react-popover'
import { FileText, X } from 'lucide-react'
import { useState } from 'react'
import { common } from '@/i18n/cs/common'
import { formatDate } from '@/lib/date'
import type { DocumentInfo } from '@/lib/domain'

function Quote({ quote }: { quote?: string }) {
  return quote ? (
    <blockquote className="mt-2 border-l-[3px] border-accent pl-3 font-mono text-sm">
      <mark className="bg-conflict-bg px-0.5 text-ink">{quote}</mark>
    </blockquote>
  ) : (
    <p className="mt-2 text-sm text-muted">{common.evidence.noQuote}</p>
  )
}

function Meta({ info }: { info: DocumentInfo }) {
  return (
    <p className="text-sm text-muted">
      {info.place ? `${info.place} · ` : ''}{common.evidence.authored} {formatDate(info.authored)} · {common.evidence.received}{' '}
      {formatDate(info.received)}
    </p>
  )
}

/** Every AI-derived value is rendered with its source: document, date and verbatim quote. */
export function EvidenceChip({
  docId,
  quote,
  doc,
  row,
}: {
  docId: string
  quote?: string
  doc?: DocumentInfo
  /** Compact variant for one value of a section: document number and date only; the title is in the tooltip. */
  row?: boolean
}) {
  const info = doc
  const [panel, setPanel] = useState(false)
  const [pop, setPop] = useState(false)
  const number = docId.slice(0, 2)
  const title = info?.title ?? docId
  return (
    <>
      <Popover.Root open={pop} onOpenChange={setPop}>
        <Popover.Trigger
          title={title}
          className="inline-flex min-h-10 max-w-full items-center gap-2 rounded-md border border-hairline bg-card px-3 text-sm text-ink transition-colors hover:border-accent hover:text-accent"
          aria-label={`${common.evidence.source}: ${title}${info ? `, ${formatDate(info.authored)}` : ''}`}
        >
          <FileText aria-hidden className="h-4 w-4 shrink-0 text-accent" />
          <span className="font-mono font-medium">{number}</span>
          {!row && <span className="max-w-[18ch] truncate font-medium">{title}</span>}
          {info && <span className="whitespace-nowrap text-xs text-muted">{formatDate(info.authored)}</span>}
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            side="bottom"
            align="start"
            sideOffset={6}
            className="z-50 w-[22rem] max-w-[calc(100vw-2rem)] rounded-md border border-hairline bg-card p-4 text-base shadow-pop"
          >
            <p className="font-semibold">{title}</p>
            {info && <Meta info={info} />}
            <p className="mt-3 text-sm font-semibold text-muted">{common.evidence.quote}</p>
            <Quote quote={quote} />
            <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
              <button
                type="button"
                className="inline-flex min-h-10 items-center rounded-md px-2 font-semibold text-accent underline underline-offset-4 hover:bg-accent-soft"
                onClick={() => {
                  setPop(false)
                  setPanel(true)
                }}
              >
                {common.evidence.open}
              </button>
              <Popover.Close className="inline-flex min-h-10 items-center rounded-md px-2 font-semibold text-accent underline underline-offset-4 hover:bg-accent-soft">{common.evidence.close}</Popover.Close>
            </div>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>

      <Dialog.Root open={panel} onOpenChange={setPanel}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/30" />
          <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-full max-w-lg space-y-4 overflow-y-auto border-l border-hairline bg-card p-6 shadow-pop sm:p-8">
            <div className="flex items-start justify-between gap-3">
              <Dialog.Title className="text-2xl font-semibold">{title}</Dialog.Title>
              <Dialog.Close aria-label={common.dialogClose} className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-md hover:bg-sunken">
                <X aria-hidden className="h-5 w-5" />
              </Dialog.Close>
            </div>
            <Dialog.Description className="sr-only">{common.evidence.panelDescription}</Dialog.Description>
            <p className="font-mono text-sm text-muted">{docId}</p>
            {info && <Meta info={info} />}
            {info?.afterAsOf && <p className="text-sm font-medium text-conflict">{common.evidence.afterAsOf}</p>}
            <h3 className="text-lg">{common.evidence.quote}</h3>
            <Quote quote={quote} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  )
}
