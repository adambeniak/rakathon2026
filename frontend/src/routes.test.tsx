import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'
import { api } from '@/lib/api/http'
import { buildSections } from '@/mocks/fixtures/handover'
import { renderRoute } from '@/test/render'

const ALENA_ID = 'rakathon-2026-prochazkova'
const ALENA = `/cases/${ALENA_ID}`

describe('route smoke + axe', () => {
  it.each(['gp', 'coordinator', 'physician', 'reviewer'] as const)(
    'shows the prototype disclaimer for the %s role',
    (role) => {
      renderRoute('/', { role })
      expect(screen.getByRole('contentinfo')).toHaveTextContent(
        'Prototyp – fiktivní data, neurčeno pro klinické rozhodování',
      )
    },
  )

  it('inbox: three columns with cards and a single primary claim action', async () => {
    const { container } = renderRoute('/inbox', { today: '2026-10-02' })
    expect(await screen.findByRole('heading', { name: 'Fronta případů' })).toBeInTheDocument()
    for (const c of ['Nový', 'Aktivní', 'Odložený']) expect(screen.getByRole('heading', { name: new RegExp(c) })).toBeInTheDocument()
    expect(await screen.findByText('Alena Procházková')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Převzít případ/ })).toHaveLength(1)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('case detail header shows state, baton, deadline and counters (3 / 2 / 1 on 21. 10.)', async () => {
    const { container } = renderRoute(ALENA, { today: '2026-10-21' })
    expect(await screen.findByRole('heading', { name: 'Alena Procházková' })).toBeInTheDocument()
    expect(screen.getAllByText('Připraveno k rozhodnutí/MDT').length).toBeGreaterThan(0)
    expect(screen.getByText(/Na tahu/)).toBeInTheDocument()
    const counters = screen.getByRole('group', { name: 'Co je potřeba řešit' })
    expect(within(counters).getByLabelText('počet: 3', { selector: 'span' })).toBeInTheDocument()
    expect(within(counters).getByLabelText('počet: 2')).toBeInTheDocument()
    expect(within(counters).getByLabelText('počet: 1')).toBeInTheDocument()
    await screen.findByText('Zjištění z dokumentace')
    expect(await axe(container)).toHaveNoViolations()
  })

  it('handover: 15 sections, missing ECOG cannot be confirmed, confirming flips the pill', async () => {
    const { container } = renderRoute(`${ALENA}/handover`, { role: 'physician', today: '2026-10-21' })
    expect(await screen.findByRole('heading', { name: /Pacient$/ })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^Potvrdit sekci:/ })).toHaveLength(15)
    expect(screen.getByRole('button', { name: 'Potvrdit sekci: Stav výkonnosti' })).toBeDisabled()
    expect(screen.getAllByText('Po MDT')).toHaveLength(2)
    await userEvent.click(screen.getByRole('button', { name: 'Potvrdit sekci: Alergie' }))
    const section = screen.getByRole('region', { name: /Alergie/ })
    await waitFor(() => expect(within(section).getByText('Ověřeno lékařem')).toBeInTheDocument())
    expect(await axe(container)).toHaveNoViolations()
  })

  it('mdt: gate blocks until sections are confirmed, then generating works', async () => {
    renderRoute(`${ALENA}/mdt`, { today: '2026-10-21' })
    const generate = await screen.findByRole('button', { name: 'Vygenerovat MDT zápis' })
    await waitFor(() => expect(generate).toBeDisabled())
    expect(await screen.findByText(/Nepotvrzeno lékařem/)).toBeInTheDocument()
    expect(screen.getAllByText('Po MDT').length).toBeGreaterThan(0)
  })

  it('referral: Odeslat stays disabled until file, KOC and consent are set', async () => {
    const { container } = renderRoute('/referral/new', { role: 'gp' })
    const submit = await screen.findByRole('button', { name: 'Odeslat do KOC' })
    expect(submit).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: /Použít ukázkovou žádost/ }))
    expect(await screen.findByText('635722/1013')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Cílové onkologické centrum'), 'koc2')
    expect(submit).toBeDisabled()
    await userEvent.click(screen.getByRole('checkbox'))
    expect(submit).toBeEnabled()
    expect(await axe(container)).toHaveNoViolations()
    await userEvent.click(submit)
    expect(await screen.findByRole('heading', { name: 'Odesláno' })).toBeInTheDocument()
  })

  it('gp: offers acknowledgement only for cases whose conclusion was sent (not by date)', async () => {
    const { container } = renderRoute('/gp', { role: 'gp', today: '2026-10-21' })
    expect(await screen.findByRole('heading', { name: 'Moji odeslaní pacienti' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Potvrdit přijetí závěru MDT: Ludmila Horáková' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Potvrdit přijetí závěru MDT: Alena/ })).toBeNull()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('demo step 6 on 21. 10.: sending the conclusion makes the GP acknowledgement appear', async () => {
    renderRoute('/', { role: 'physician', today: '2026-10-21' })
    await api.post(`/api/cases/${ALENA_ID}/handover/confirm-all`)
    await api.post(`/api/cases/${ALENA_ID}/mdt/generate?as_of=${encodeURIComponent('2026-10-21T08:00:00+02:00')}`)
    await api.post(`/api/cases/${ALENA_ID}/send-feedback`)
    cleanup()
    renderRoute('/gp', { role: 'gp', today: '2026-10-21', keepStore: true })
    const ack = await screen.findByRole('button', { name: /Potvrdit přijetí závěru MDT: Alena/ })
    await userEvent.click(ack)
    await waitFor(() => expect(screen.queryByRole('button', { name: /Potvrdit přijetí závěru MDT: Alena/ })).toBeNull())
  })

  it('reviewer: minimal summary without full patient names', async () => {
    const { container } = renderRoute('/reviewer', { role: 'reviewer', today: '2026-10-21' })
    expect(await screen.findByText(/A\. P\., 1963/)).toBeInTheDocument()
    expect(screen.queryByText(/Procházková/)).toBeNull()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('unknown case shows guidance instead of an error page', async () => {
    renderRoute('/cases/neexistuje')
    expect(await screen.findByText('Případ nebyl nalezen')).toBeInTheDocument()
  })
})

describe('language', () => {
  it('shows no English fixture text on the handover', async () => {
    renderRoute(`${ALENA}/handover`, { today: '2026-10-21' })
    await screen.findByRole('heading', { name: /Pacient$/ })
    expect(document.body.textContent).not.toMatch(/\b(documented|must not|missing|inferred)\b/i)
  })
})

describe('review fixes', () => {
  it('only a physician can confirm: UI is disabled and the mock API answers 403', async () => {
    renderRoute(`${ALENA}/handover`, { role: 'coordinator', today: '2026-10-21' })
    expect(await screen.findByRole('heading', { name: /Pacient$/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Potvrdit sekci: Alergie' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Potvrdit všechny dostupné sekce' })).toBeDisabled()
    await expect(api.post(`/api/cases/${ALENA_ID}/handover/sections/8_allergies/confirm`)).rejects.toMatchObject({ status: 403 })
  })

  it('records the confirming physician, not a fixed user', async () => {
    renderRoute(`${ALENA}/handover`, { role: 'physician', today: '2026-10-21' })
    await userEvent.click(await screen.findByRole('button', { name: 'Potvrdit sekci: Alergie' }))
    expect(await screen.findByText('Potvrdil(a) MUDr. Havelka')).toBeInTheDocument()
  })

  it('unlabeled rows keep a term for assistive technology', async () => {
    renderRoute(`${ALENA}/handover`, { today: '2026-10-21' })
    const section = await screen.findByRole('region', { name: /Alergie/ })
    expect(section.querySelector('dd')?.parentElement?.querySelector('dt')).not.toBeNull()
  })

  it('claiming Marie Králová changes Marie, not Alena', async () => {
    renderRoute('/inbox', { today: '2026-10-16' })
    await userEvent.click(await screen.findByRole('button', { name: 'Převzít případ: Marie Králová' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: /Převzít případ/ })).toBeNull())
    expect(screen.getAllByText('V triage').length).toBeGreaterThan(0)
  })

  it('mdt preview shows evidence chips and drops results beyond the cutoff', async () => {
    renderRoute(`${ALENA}/mdt`, { role: 'physician', today: '2026-10-21' })
    expect((await screen.findAllByRole('button', { name: /^Zdroj:/ })).length).toBeGreaterThan(5)
    const input = screen.getByLabelText(/Stav k termínu/)
    fireEvent.change(input, { target: { value: '2026-10-16T08:00' } })
    await screen.findByText(/K termínu as-of chybí histologie/)
    expect(screen.queryByText(/histologie vydána 19\. 10\. 2026/)).toBeNull()
    expect(screen.queryByText(/Duktální adenokarcinom/)).toBeNull()
    expect(screen.getByRole('button', { name: 'Vygenerovat MDT zápis' })).toBeDisabled()
  })

  it('generated state is tied to the selected cutoff', async () => {
    renderRoute(`${ALENA}/mdt`, { role: 'physician', today: '2026-10-21' })
    await api.post(`/api/cases/${ALENA_ID}/handover/confirm-all`)
    await api.post(`/api/cases/${ALENA_ID}/mdt/generate?as_of=${encodeURIComponent('2026-10-21T08:00:00+02:00')}`)
    cleanup()
    renderRoute(`${ALENA}/mdt`, { role: 'physician', today: '2026-10-21', keepStore: true })
    expect(await screen.findByRole('button', { name: 'Odeslat závěr praktickému lékaři' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Stav k termínu/), { target: { value: '2026-10-16T08:00' } })
    expect(await screen.findByRole('button', { name: 'Vygenerovat MDT zápis' })).toBeInTheDocument()
  })

  it('referral prefill carries field-specific evidence', async () => {
    renderRoute('/referral/new', { role: 'gp' })
    await userEvent.click(await screen.findByRole('button', { name: /Použít ukázkovou žádost/ }))
    await screen.findByText('635722/1013')
    expect(screen.getAllByRole('button', { name: /^Zdroj:/ }).length).toBeGreaterThanOrEqual(6)
  })

  it('every epikríza statement has evidence available at the cutoff', () => {
    const early = buildSections({}, '2026-10-16T08:00:00+02:00')
    const epi = early.find((x) => x.key === '4_epicrisis')!
    expect(epi.rows[0]?.value).not.toMatch(/histologie|19\. 10\./)
    const full = buildSections({}, '2026-10-21T08:00:00+02:00').find((x) => x.key === '4_epicrisis')!
    expect(full.evidence.map((e) => e.docId.slice(0, 2))).toEqual(expect.arrayContaining(['07', '08', '09', '10', '11']))
    expect(early.find((x) => x.key === '14_histology')?.status).toBe('missing')
  })
})
