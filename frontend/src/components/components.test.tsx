import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CaseStateBadge } from './CaseStateBadge'
import { EvidenceChip } from './EvidenceChip'
import { StatusPill, pillForHandover } from './StatusPill'
import { CASE_STATES } from '@/lib/domain'

describe('StatusPill', () => {
  it.each([
    ['missing', 'Chybí'],
    ['conflict', 'Nesouhlasí'],
    ['stale', 'Zastaralé'],
    ['verified', 'Potvrzeno lékařem'],
    ['ai', 'Návrh AI'],
  ] as const)('renders text %s with an icon', (kind, text) => {
    const { container } = render(<StatusPill kind={kind} />)
    expect(screen.getByText(text)).toBeInTheDocument()
    expect(container.querySelector('svg')).not.toBeNull()
  })

  it('marks unconfirmed AI output as draft and confirmed as verified', () => {
    expect(pillForHandover('complete', false)).toEqual(['ai'])
    expect(pillForHandover('complete', true)).toEqual(['verified'])
    expect(pillForHandover('missing', false)).toEqual(['missing'])
    expect(pillForHandover('complete_with_conflict', false)).toEqual(['ai', 'conflict'])
  })
})

describe('CaseStateBadge', () => {
  it.each(CASE_STATES)('renders state %s', (state) => {
    const { unmount } = render(<CaseStateBadge state={state} />)
    expect(document.body.textContent).toMatch(/\d\/8/)
    unmount()
  })
  it('marks the current step in the stepper', () => {
    render(<CaseStateBadge state="ceka_na_podklady" variant="stepper" />)
    expect(screen.getAllByText('Čeká na podklady').length).toBeGreaterThan(0)
    expect(document.querySelector('[aria-current="step"]')).not.toBeNull()
  })
})

describe('EvidenceChip', () => {
  it('shows document, date and verbatim quote on click', async () => {
    const doc = { id: '07_x', title: 'Žádost PL', place: 'Ordinace', authored: '2026-10-02', received: '2026-10-02T10:00:00+02:00', afterAsOf: false }
    render(<EvidenceChip docId="07_x" quote="AA: neguje" doc={doc} />)
    await userEvent.click(screen.getByRole('button', { name: /Zdroj: Žádost PL, 2. 10. 2026/ }))
    expect(await screen.findByText('AA: neguje')).toBeInTheDocument()
  })
  it('says so when no quote is stored', async () => {
    render(<EvidenceChip docId="10_x" />)
    await userEvent.click(screen.getByRole('button'))
    expect(await screen.findByText(/Doslovná citace chybí/)).toBeInTheDocument()
  })
})
