import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'
import { adaptCase } from '@/features/cases/adapter'
import type { components } from '@/lib/api/schema'
import { renderRoute } from '@/test/render'

const ALENA = '/cases/rakathon-2026-prochazkova'

describe('contract adapter', () => {
  const base: components['schemas']['CaseSummary'] = {
    id: 'x',
    patient: { display_name: 'Test Pacient', birth_date: '1970-01-01', age_years: 56, sex: 'unknown' },
    state: 'odeslano',
    document_count: 0,
  }

  it('keeps counts the backend has not computed as null (never 0) and leaves unknown fields undefined', () => {
    const c = adaptCase(base)
    expect(c.counts).toEqual({ missing: null, conflict: null, stale: null })
    expect(c.insurerCode).toBeNull()
    expect(c.diagnosis).toBeUndefined()
    expect(c.baton).toBeNull()
    expect(c.column).toBe('new')
  })

  it('derives baton action and queue column from the state code', () => {
    const c = adaptCase({
      ...base,
      state: 'kompletni',
      baton_holder: { display: 'MUDr. Havelka', id: 'h', role: 'koc_physician' },
      next_deadline: '2026-10-21T08:00:00+02:00',
    })
    expect(c.column).toBe('active')
    expect(c.baton).toEqual({ name: 'MUDr. Havelka', action: 'Zkontrolovat a potvrdit předání', due: '2026-10-21T08:00:00+02:00' })
  })
})

describe('inbox', () => {
  it('sorts each column by deadline, earliest first', async () => {
    renderRoute('/inbox', { today: '2026-10-16' })
    await screen.findByText('Marie Králová')
    const col = screen.getByRole('heading', { name: /Aktivní/ }).closest('section')!
    const names = within(col)
      .getAllByRole('article')
      .map((a) => a.getAttribute('aria-label'))
    // Svoboda is due 20. 10., Dvořák 22. 10.: the earlier deadline comes first.
    expect(names.indexOf('Petr Svoboda')).toBeGreaterThanOrEqual(0)
    expect(names.indexOf('Petr Svoboda')).toBeLessThan(names.indexOf('Jan Dvořák'))
    expect(within(screen.getByRole('heading', { name: /Nový/ }).closest('section')!).getByText('Marie Králová')).toBeInTheDocument()
  })
})

describe('demo steps 2 and 4', () => {
  it('claim → triage checklist → one click requests the selected documents', async () => {
    renderRoute(ALENA, { today: '2026-10-02' })
    await userEvent.click(await screen.findByRole('button', { name: 'Převzít případ: Alena Procházková' }))
    expect(await screen.findByRole('heading', { name: 'Chybějící podklady k vyžádání' })).toBeInTheDocument()
    expect(screen.getAllByRole('checkbox')).toHaveLength(6)
    expect(screen.getAllByText(/Adresát:/)).toHaveLength(6)
    await userEvent.click(screen.getAllByRole('checkbox')[0]!) // deselect one
    await userEvent.click(screen.getByRole('button', { name: 'Vyžádat vybrané' }))
    await waitFor(() => expect(screen.getAllByText('Čeká na podklady').length).toBeGreaterThan(0))
    expect(screen.getAllByText('Vyžádáno')).toHaveLength(5)
  })

  it('task set: empty until started, then a five-lane board with blocking dependencies', async () => {
    const { container } = renderRoute(`${ALENA}/tasks`, { today: '2026-10-02' })
    expect(await screen.findByText('Žádné úkoly')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Spustit sadu: Karcinom pankreatu – diagnostika' }))
    const board = await screen.findByRole('group', { name: 'Kdo je na tahu' })
    for (const lane of ['PL', 'Koordinátor', 'Lékař KOC', 'Externí pracoviště', 'Pacient']) {
      expect(within(board).getByRole('heading', { name: lane })).toBeInTheDocument()
    }
    expect(within(board).getAllByText(/^Čeká na:/).length).toBeGreaterThan(0)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('task actions advance a task and respect dependencies', async () => {
    renderRoute(`${ALENA}/tasks`, { today: '2026-10-02' })
    await userEvent.click(await screen.findByRole('button', { name: /^Spustit sadu/ }))
    const order = await screen.findByRole('button', { name: /^Potvrdit objednání: CT hrudníku/ })
    // EUS-FNB depends on the CT: its action is disabled until the CT is performed.
    expect(screen.getByRole('button', { name: /^Potvrdit objednání: EUS-FNB/ })).toBeDisabled()
    await userEvent.click(order)
    const performed = await screen.findByRole('button', { name: /^Označit jako provedené: CT hrudníku/ })
    await userEvent.click(performed)
    // Performed is not done: the result must be delivered before the dependent task unblocks.
    expect(screen.getByRole('button', { name: /^Potvrdit objednání: EUS-FNB/ })).toBeDisabled()
    await userEvent.click(await screen.findByRole('button', { name: /^Potvrdit doručení výsledku: CT hrudníku/ }))
    await waitFor(() => expect(screen.getByRole('button', { name: /^Potvrdit objednání: EUS-FNB/ })).toBeEnabled())
  })
})

describe('header action', () => {
  it('offers "Připravit MDT" to the physician once the case is ready', async () => {
    renderRoute(ALENA, { role: 'physician', today: '2026-10-21' })
    const link = await screen.findByRole('link', { name: 'Připravit MDT' })
    expect(link).toHaveAttribute('href', `${ALENA}/mdt`)
  })

  it('shows who holds the baton and until when', async () => {
    renderRoute(ALENA, { role: 'physician', today: '2026-10-21' })
    expect(await screen.findByText(/Na tahu:/)).toBeInTheDocument()
    expect(screen.getAllByText(/^do 21\. 10\. 2026/).length).toBeGreaterThan(0)
  })
})

describe('handover review', () => {
  it('sticky summary bar keeps the AI-draft label until everything is confirmed', async () => {
    renderRoute(`${ALENA}/handover`, { role: 'physician', today: '2026-10-21' })
    const bar = await screen.findByRole('group', { name: 'Souhrn handoveru' })
    expect(within(bar).getByText('Návrh AI – čeká na potvrzení lékařem')).toBeInTheDocument()
    expect(within(bar).getByText(/^Potvrzeno: 0 z /)).toBeInTheDocument()
    expect(within(bar).getByText('Chybí').nextElementSibling).toHaveTextContent('3')
    expect(within(bar).getByText('Nesouhlasí').nextElementSibling).toHaveTextContent('2')
    await userEvent.click(screen.getByRole('button', { name: 'Potvrdit všechny dostupné sekce' }))
    await within(bar).findByText(/Dostupné sekce potvrzeny lékařem · chybí údaje v sekcích: \d+/)
    expect(within(bar).queryByText('Návrh AI – čeká na potvrzení lékařem')).toBeNull()
  })

  it('inline edit needs a reason, is recorded on the value and resets the confirmation', async () => {
    renderRoute(`${ALENA}/handover`, { role: 'physician', today: '2026-10-21' })
    await userEvent.click(await screen.findByRole('button', { name: 'Potvrdit sekci: Alergie' }))
    await screen.findByText('Potvrdil(a) MUDr. Havelka')
    await userEvent.click(screen.getByRole('button', { name: 'Upravit sekci: Alergie' }))
    const section = screen.getByRole('region', { name: /Alergie/ })
    const input = within(section).getAllByRole('textbox', { name: /^Hodnota:/ })[0]!
    await userEvent.clear(input)
    await userEvent.type(input, 'Bez známých alergií')
    expect(within(section).getByRole('button', { name: 'Uložit změnu' })).toBeDisabled() // no reason yet
    await userEvent.type(within(section).getByLabelText('Důvod změny'), 'Upřesněno s pacientkou')
    await userEvent.click(within(section).getByRole('button', { name: 'Uložit změnu' }))
    expect(await within(section).findByText(/Upraveno lékařem .*důvod: Upřesněno s pacientkou/)).toBeInTheDocument()
    expect(within(section).queryByText('Potvrdil(a) MUDr. Havelka')).toBeNull()
  })

  it('evidence chip opens the source document in a side panel', async () => {
    renderRoute(`${ALENA}/handover`, { role: 'physician', today: '2026-10-21' })
    const chips = await screen.findAllByRole('button', { name: /^Zdroj:/ })
    await userEvent.click(chips[0]!)
    await userEvent.click(await screen.findByRole('button', { name: 'Zobrazit zdroj a citaci' }))
    const panel = await screen.findByRole('dialog')
    expect(within(panel).getByText('Citace z dokumentu')).toBeInTheDocument()
  })
})

describe('API-decided rendering', () => {
  it('consent rows are read-only and show their source chip', async () => {
    renderRoute(`${ALENA}/handover`, { role: 'physician', today: '2026-10-21' })
    await userEvent.click(await screen.findByRole('button', { name: 'Upravit sekci: Jiná sdělení' }))
    const section = screen.getByRole('region', { name: /Jiná sdělení/ })
    expect(within(section).getByText('Souhlasí se sdílením informací s dcerou.')).toBeInTheDocument()
    expect(within(section).getByText('Souhlas pacienta – nelze upravit')).toBeInTheDocument()
    // The consent row has a source chip and no input; the other rows are editable.
    const inputs = within(section).getAllByRole('textbox', { name: /^Hodnota:/ })
    expect(inputs.length).toBeGreaterThan(0)
    expect(inputs.some((i) => (i as HTMLInputElement).value.startsWith('Souhlasí'))).toBe(false)
  })

  it('triage hint shows the evidence chip returned with the proposals', async () => {
    renderRoute(ALENA, { today: '2026-10-02' })
    await userEvent.click(await screen.findByRole('button', { name: 'Převzít případ: Alena Procházková' }))
    const panel = await screen.findByRole('heading', { name: 'Chybějící podklady k vyžádání' })
    expect(within(panel.closest('section')!).getAllByRole('button', { name: /^Zdroj:/ }).length).toBeGreaterThan(0)
  })

  it('documents tab marks "Po MDT" from the handover data, not from dates', async () => {
    renderRoute(`${ALENA}/documents`, { today: '2026-10-27' })
    await screen.findByText('Algeziologické vyšetření')
    await waitFor(() => expect(screen.getAllByText('Po MDT')).toHaveLength(2))
  })
})

describe('referral confirmation', () => {
  it('sends the optional note and explains what happens next', async () => {
    renderRoute('/referral/new', { role: 'gp' })
    await userEvent.click(await screen.findByRole('button', { name: /Použít ukázkovou žádost/ }))
    await screen.findByText('635722/1013')
    await userEvent.selectOptions(screen.getByLabelText('Cílové onkologické centrum'), 'koc2')
    await userEvent.click(screen.getByRole('checkbox'))
    await userEvent.type(screen.getByLabelText(/Poznámka pro koordinaci/), 'Pacientka je k zastižení odpoledne.')
    await userEvent.click(screen.getByRole('button', { name: 'Odeslat do KOC' }))
    expect(await screen.findByRole('heading', { name: 'Odesláno' })).toBeInTheDocument()
    expect(screen.getByText('Stav případu:')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Co bude dál' })).toBeInTheDocument()
  })
})
