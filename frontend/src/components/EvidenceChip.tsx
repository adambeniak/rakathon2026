import * as Dialog from '@radix-ui/react-dialog'
import * as Popover from '@radix-ui/react-popover'
import { FileText, X } from 'lucide-react'
import { useState } from 'react'
import { common } from '@/i18n/cs/common'
import { formatDate } from '@/lib/date'
import type { DocumentInfo } from '@/lib/domain'

function Quote({ quote }: { quote?: string }) {
  return quote ? (
    <blockquote className="mt-1 border-l-2 border-accent pl-2 font-mono text-xs">
      <mark className="bg-conflict-bg px-0.5 text-ink">{quote}</mark>
    </blockquote>
  ) : (
    <p className="mt-1 text-xs text-muted">{common.evidence.noQuote}</p>
  )
}

function Meta({ info }: { info: DocumentInfo }) {
  return (
    <p className="text-xs text-muted">
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
          className="inline-flex min-h-6 items-center gap-1 rounded border border-hairline bg-card px-2 py-1 text-xs hover:bg-accent-soft"
          aria-label={`${common.evidence.source}: ${title}${info ? `, ${formatDate(info.authored)}` : ''}`}
        >
          <FileText aria-hidden className="h-3 w-3 text-accent" />
          <span className="font-mono">{number}</span>
          {!row && <span className="max-w-[16ch] truncate">{title}</span>}
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
            {info && <Meta info={info} />}
            <p className="mt-2 text-xs font-medium text-muted">{common.evidence.quote}</p>
            <Quote quote={quote} />
            <div className="mt-3 flex items-center gap-3 text-xs">
              <button
                type="button"
                className="font-medium text-accent underline"
                onClick={() => {
                  setPop(false)
                  setPanel(true)
                }}
              >
                {common.evidence.open}
              </button>
              <Popover.Close className="text-accent underline">{common.evidence.close}</Popover.Close>
            </div>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>

      <Dialog.Root open={panel} onOpenChange={setPanel}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/30" />
          <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-full max-w-md space-y-3 overflow-y-auto border-l border-hairline bg-card p-6 shadow-xl">
            <div className="flex items-start justify-between gap-3">
              <Dialog.Title className="font-serif text-2xl">{title}</Dialog.Title>
              <Dialog.Close aria-label={common.dialogClose} className="rounded p-1 hover:bg-accent-soft">
                <X aria-hidden className="h-5 w-5" />
              </Dialog.Close>
            </div>
            <Dialog.Description className="sr-only">{common.evidence.panelDescription}</Dialog.Description>
            <p className="font-mono text-xs text-muted">{docId}</p>
            {info && <Meta info={info} />}
            {info?.afterAsOf && <p className="text-sm font-medium text-conflict">{common.evidence.afterAsOf}</p>}
            <h3 className="text-base">{common.evidence.quote}</h3>
            <Quote quote={quote} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  )
}
