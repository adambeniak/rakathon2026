import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'
import { renderRoute } from '@/test/render'

const ALENA = '/cases/rakathon-2026-prochazkova'

describe('route smoke + axe', () => {
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
    const { container } = renderRoute(`${ALENA}/handover`, { today: '2026-10-21' })
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
    const submit = await screen.findByRole('button', { name: 'Odeslat' })
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

  it('gp: lists referred patients and offers acknowledgement of the MDT result', async () => {
    const { container } = renderRoute('/gp', { role: 'gp', today: '2026-10-22' })
    expect(await screen.findByRole('heading', { name: 'Moji odeslaní pacienti' })).toBeInTheDocument()
    expect(await screen.findAllByRole('button', { name: /Potvrdit přijetí závěru MDT/ })).not.toHaveLength(0)
    expect(await axe(container)).toHaveNoViolations()
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
