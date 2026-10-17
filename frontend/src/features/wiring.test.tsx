import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { adaptCase } from '@/features/cases/adapter'
import type { components } from '@/lib/api/schema'
import { server } from '@/mocks/server'
import { problem } from '@/mocks/handlers/util'
import { renderRoute } from '@/test/render'

const ALENA = '/cases/rakathon-2026-prochazkova'

describe('contract adapter', () => {
  const base: components['schemas']['CaseSummary'] = {
    id: 'x',
    patient: { display_name: 'Test Pacient', birth_date: '1970-01-01', age_years: 56, sex: 'unknown' },
    state: 'odeslano',
    bucket: 'novy',
    postponed: false,
    document_count: 0,
  }

  it('keeps counts the backend has not computed as null (never 0) and leaves unknown fields undefined', () => {
    const c = adaptCase(base)
    expect(c.counts).toEqual({ missing: null, conflict: null, stale: null }) // not computed: never 0
    expect(c.insurerCode).toBeNull()
    expect(c.diagnosis).toBeUndefined()
    expect(c.baton).toBeNull()
    expect(c.column).toBe('new')
    expect(adaptCase({ ...base, bucket: 'odlozeny', postponed: true }).column).toBe('snoozed')
  })

  it('derives baton action and queue column from the state code', () => {
    const c = adaptCase({
      ...base,
      state: 'kompletni',
      bucket: 'aktivni',
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
    // The five reports the letter lists (01, 02, 03, 05, 06); the GP's own epicrisis (04) is not proposed.
    expect(screen.getAllByRole('checkbox')).toHaveLength(5)
    expect(screen.getAllByText(/Adresát:/)).toHaveLength(5)
    expect(screen.queryByText(/epikr/i)).toBeNull()
    await userEvent.click(screen.getAllByRole('checkbox')[0]!) // deselect one
    await userEvent.click(screen.getByRole('button', { name: 'Vyžádat vybrané' }))
    await waitFor(() => expect(screen.getAllByText('Čeká na podklady').length).toBeGreaterThan(0))
    expect(await screen.findAllByText('Vyžádáno')).toHaveLength(4)
  })

  it('the case overview does not call /findings (they are shown on the handover) and has no error box', async () => {
    const calls: string[] = []
    server.use(
      http.get('/api/cases/:id/findings', ({ request }) => {
        calls.push(request.url)
        return problem(404, 'Not Found')
      }),
    )
    renderRoute(ALENA, { today: '2026-10-21' })
    expect(await screen.findByText('Zjištění z dokumentace')).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Otevřít handover' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(calls).toEqual([])
  })

  it('claim shows the problem title when the backend refuses', async () => {
    server.use(http.post('/api/cases/:id/transitions', () => problem(409, 'Případ už byl převzat jiným koordinátorem')))
    renderRoute(ALENA, { today: '2026-10-02' })
    await userEvent.click(await screen.findByRole('button', { name: 'Převzít případ: Alena Procházková' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Případ se nepodařilo převzít. Případ už byl převzat jiným koordinátorem')
  })

  it('claim from the inbox turns the case into triage', async () => {
    renderRoute('/inbox', { today: '2026-10-02' })
    await userEvent.click(await screen.findByRole('button', { name: 'Převzít případ: Alena Procházková' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: /Převzít případ: Alena/ })).toBeNull())
    expect(within(screen.getByRole('article', { name: 'Alena Procházková' })).getByText('V triage')).toBeInTheDocument()
  })

  it('a proposal without a resolved workplace cannot be requested, an attached report is not offered again', async () => {
    server.use(
      http.get('/api/cases/:id/document-requests/proposals', () =>
        HttpResponse.json({
          source_doc_id: '07_PL_zadost_KOC2_2026-10-02',
          proposals: [
            { key: 'a', label: 'MR mozku 5. 9. 2026 (Neznámé centrum Brno)', exam_date: '2026-09-05', status: 'missing', recipient_org_id: null, evidence: [{ doc_id: '07_PL_zadost_KOC2_2026-10-02', quote: '1. MR mozku 5. 9. 2026 (Neznámé centrum Brno)' }] },
            { key: 'b', label: 'RTG plic 3. 9. 2026', exam_date: '2026-09-03', status: 'attached', attached_doc_id: '03_RTG_plic_2026-09-03', recipient_org_id: 'rc-modrany', evidence: [{ doc_id: '07_PL_zadost_KOC2_2026-10-02', quote: '2. RTG plic 3. 9. 2026' }] },
          ],
        }),
      ),
    )
    renderRoute(ALENA, { today: '2026-10-02' })
    await userEvent.click(await screen.findByRole('button', { name: 'Převzít případ: Alena Procházková' }))
    await screen.findByRole('heading', { name: 'Chybějící podklady k vyžádání' })
    const [unresolved, attached] = screen.getAllByRole('checkbox')
    expect(unresolved).toBeDisabled()
    expect(unresolved).not.toBeChecked()
    expect(attached).toBeDisabled()
    expect(screen.getByText('Již v případu')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Vyžádat vybrané' })).toBeDisabled()
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
    expect(within(bar).getByText('Návrh AI – čeká na potvrzení')).toBeInTheDocument()
    expect(within(bar).getByText(/^Potvrzeno lékařem: 0 z /)).toBeInTheDocument()
    expect(within(bar).getByText('Chybí').nextElementSibling).toHaveTextContent('3')
    expect(within(bar).getByText('Nesouhlasí').nextElementSibling).toHaveTextContent('2')
    // There is no bulk confirmation: the physician confirms the sections one by one and accepts the missing one.
    expect(screen.queryByRole('button', { name: /Potvrdit všechny/ })).toBeNull()
    const names = screen.getAllByRole('button', { name: /^Potvrdit sekci:/ }).map((b) => b.getAttribute('aria-label')!)
    for (const name of names) await userEvent.click(screen.getByRole('button', { name }))
    await userEvent.click(screen.getByRole('button', { name: 'Ponechat údaj v sekci Stav výkonnosti jako chybějící' }))
    await within(bar).findByText('Všechny sekce potvrzeny lékařem · ponecháno jako chybějící: 1')
    expect(within(bar).queryByText('Návrh AI – čeká na potvrzení')).toBeNull()
    expect(within(bar).getByText('Potvrzeno lékařem: 15 z 15')).toBeInTheDocument()
  })

  it('inline edit of a plain-text section saves and confirms in one step, without a reason field', async () => {
    renderRoute(`${ALENA}/handover`, { role: 'physician', today: '2026-10-21' })
    await userEvent.click(await screen.findByRole('button', { name: 'Upravit sekci: Alergie' }))
    const section = screen.getByRole('region', { name: /Alergie/ })
    expect(within(section).queryByLabelText('Důvod změny')).toBeNull()
    const input = within(section).getByRole('textbox', { name: /^Hodnota:/ })
    await userEvent.clear(input)
    await userEvent.type(input, 'Bez známých alergií')
    await userEvent.click(within(section).getByRole('button', { name: 'Uložit a potvrdit' }))
    expect(await within(section).findByText('Bez známých alergií')).toBeInTheDocument()
    expect(within(section).getByText('Upraveno lékařem', { selector: 'span' })).toBeInTheDocument()
    expect(within(section).getByText('Potvrdil(a) MUDr. Havelka')).toBeInTheDocument()
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
  it('consent rows are read-only: shown with their source chip, the section has no edit', async () => {
    renderRoute(`${ALENA}/handover`, { role: 'physician', today: '2026-10-21' })
    const section = await screen.findByRole('region', { name: /Jiná sdělení/ })
    expect(within(section).getByText('Souhlasí se sdílením informací s dcerou.')).toBeInTheDocument()
    expect(within(section).getByText('Souhlas pacienta – nelze upravit')).toBeInTheDocument()
    expect(within(section).getAllByRole('button', { name: /^Zdroj:/ }).length).toBeGreaterThan(0)
    expect(within(section).queryByRole('button', { name: /^Upravit sekci/ })).toBeNull()
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
  it('preselects the priority only from the letter, shows missing values as Chybí and blocks sending without required data', async () => {
    server.use(
      http.post('/api/referrals/prefill', () => {
        const none = { value: null, status: 'missing', derived: false, evidence: [] }
        return HttpResponse.json({ doc_id: 'x', given: none, family: none, sex: none, birth_date: none, age_text: none, birth_number: none, address: none, patient_phone: none, insurer_code: none, contact_person: none, requesting_gp: none, suspected_diagnosis: none, consent_statements: [], urgency_statement: none })
      }),
    )
    renderRoute('/referral/new', { role: 'gp' })
    await userEvent.click(await screen.findByRole('button', { name: /Použít ukázkovou žádost/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('V žádosti nejsou uvedeny povinné údaje')
    expect(screen.getAllByText('Chybí').length).toBeGreaterThan(5)
    expect(screen.getByLabelText(/Naléhavost žádosti/)).toHaveValue('routine') // never assumed
    await userEvent.selectOptions(screen.getByLabelText('Cílové onkologické centrum'), 'koc2-nemocnice-lipova')
    await userEvent.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: 'Odeslat do KOC' })).toBeDisabled()
  })

  it('preselects Urgentní when the letter asks for it, and shows the problem title when sending fails', async () => {
    server.use(http.post('/api/referrals', () => problem(403, 'Žádost může odeslat pouze praktický lékař')))
    renderRoute('/referral/new', { role: 'gp' })
    await userEvent.click(await screen.findByRole('button', { name: /Použít ukázkovou žádost/ }))
    await screen.findByText('635722/1013')
    expect(screen.getByLabelText(/Naléhavost žádosti/)).toHaveValue('urgent')
    expect(screen.getByText('Souhlasí se sdílením informací s dcerou.')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Cílové onkologické centrum'), 'koc2-nemocnice-lipova')
    await userEvent.click(screen.getByRole('checkbox'))
    await userEvent.click(screen.getByRole('button', { name: 'Odeslat do KOC' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Žádost se nepodařilo odeslat. Žádost může odeslat pouze praktický lékař')
  })

  it('sends the optional note and explains what happens next', async () => {
    renderRoute('/referral/new', { role: 'gp' })
    await userEvent.click(await screen.findByRole('button', { name: /Použít ukázkovou žádost/ }))
    await screen.findByText('635722/1013')
    await userEvent.selectOptions(screen.getByLabelText('Cílové onkologické centrum'), 'koc2-nemocnice-lipova')
    await userEvent.click(screen.getByRole('checkbox'))
    await userEvent.type(screen.getByLabelText(/Poznámka pro koordinaci/), 'Pacientka je k zastižení odpoledne.')
    await userEvent.click(screen.getByRole('button', { name: 'Odeslat do KOC' }))
    expect(await screen.findByRole('heading', { name: 'Odesláno' })).toBeInTheDocument()
    expect(screen.getByText('Stav případu:')).toBeInTheDocument()
    expect(screen.getByText('Odesláno', { selector: 'span' })).toBeInTheDocument() // state from the created case
    expect(screen.getByText('Koordinátor KOC 2')).toBeInTheDocument() // who holds the baton
    expect(screen.getByRole('link', { name: 'Otevřít případ' })).toHaveAttribute('href', '/cases/rakathon-2026-prochazkova')
    expect(screen.getByRole('heading', { name: 'Co bude dál' })).toBeInTheDocument()
  })
})
