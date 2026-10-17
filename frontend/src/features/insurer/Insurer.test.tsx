import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { axe } from 'vitest-axe'
import { INSURER_ANALYTICS } from '@/mocks/fixtures/insurer'
import { problem } from '@/mocks/handlers/util'
import { server } from '@/mocks/server'
import { renderRoute } from '@/test/render'

const NBSP = new RegExp(String.fromCharCode(160), 'g')

describe('Insurer analytics (ZP 211, simulated cohort)', () => {
  it('shows the simulated-data notice, key facts and hospitals ranked by the API indicator', async () => {
    const { container } = renderRoute('/insurer', { role: 'reviewer', today: '2026-10-21' })

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Analytika péče pro ZP 211' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent(
      /Simulovaná data – fiktivní kohorta pro demo, ilustrativní ceník/,
    )

    const table = await screen.findByRole('table', { name: /Nemocnice seřazené podle provozního indikátoru/ })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.map((r) => within(r).getByRole('rowheader').textContent)).toEqual(
      INSURER_ANALYTICS.hospitals.map((h) => expect.stringContaining(h.name) as unknown as string),
    )
    // the top hospital carries both badges as icon + text, and its indicator is rendered as text
    const top = rows[0]
    if (!top) throw new Error('no hospital rows')
    expect(within(top).getByText('Nejrychlejší v kohortě')).toBeInTheDocument()
    expect(within(top).getByText('Nejnižší náklady v kohortě')).toBeInTheDocument()
    expect(within(top).getByText('100')).toBeInTheDocument()
    // Czech currency format, e.g. "27 850 Kč"
    expect(top.textContent?.replace(NBSP, ' ')).toContain('27 850 Kč')

    expect(await axe(container)).toHaveNoViolations()
  })

  it('explains the indicator with weights, targets and the capacity assumption from the API', async () => {
    renderRoute('/insurer', { role: 'reviewer', today: '2026-10-21' })

    const details = (await screen.findByText('Jak se provozní indikátor počítá')).closest('details')
    expect(details).not.toBeNull()
    const text = details?.textContent?.replace(NBSP, ' ') ?? ''
    expect(text).toContain('rychlost 50 %, náklady 30 %, podíl případů v cílových lhůtách 20 %')
    expect(text).toContain('CT do 7 dní od objednání a biopsie do 10 dní od objednání')
    expect(text).toContain('Předpoklad pro demo')
    expect(text).toContain('120 min týdně')
  })

  it('lists the demo case first with Czech dates, day chips and "nezaznamenáno" for missing steps', async () => {
    renderRoute('/insurer', { role: 'reviewer', today: '2026-10-21' })

    const demo = (
      await screen.findByRole('heading', { level: 3, name: 'rakathon-2026-prochazkova' })
    ).closest('article')
    expect(demo).not.toBeNull()
    const card = within(demo as HTMLElement)
    expect(card.getByText('Demo případ')).toBeInTheDocument()
    expect(card.getByText('8. 10. 2026')).toBeInTheDocument() // CT
    expect(card.getByText('12. 10. 2026')).toBeInTheDocument() // biopsy
    expect(card.getByText('21. 10. 2026')).toBeInTheDocument() // MDT
    expect(card.getByText('+4 dny')).toBeInTheDocument() // CT -> biopsy
    expect(card.getByText('+9 dní')).toBeInTheDocument() // biopsy -> MDT
    expect(card.getAllByText('nezaznamenáno')).toHaveLength(2) // acceptance and treatment start
    const firstArticle = screen.getAllByRole('article')[0]
    expect(firstArticle).toBe(demo)
  })

  it('shows the coordinators table', async () => {
    renderRoute('/insurer', { role: 'reviewer', today: '2026-10-21' })

    const table = await screen.findByRole('table', { name: /čas koordinátora na pacienta/ })
    expect(
      within(table).getByRole('rowheader', { name: 'Bc. Lucie Dvořáková' }),
    ).toBeInTheDocument()
  })

  it('tells other roles the view is for the insurer reviewer only', async () => {
    renderRoute('/insurer', { role: 'coordinator', today: '2026-10-21' })

    expect(
      await screen.findByText(
        'Analytika péče je dostupná jen reviznímu lékaři zdravotní pojišťovny.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows the error state with a retry on a server failure', async () => {
    server.use(http.get('/api/insurer/analytics', () => problem(500, 'Neočekávaná chyba serveru')))
    renderRoute('/insurer', { role: 'reviewer', today: '2026-10-21' })

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('shows the empty state for a cohort without journeys', async () => {
    server.use(
      http.get('/api/insurer/analytics', () =>
        HttpResponse.json({ ...INSURER_ANALYTICS, hospitals: [], coordinators: [], journeys: [] }),
      ),
    )
    renderRoute('/insurer', { role: 'reviewer', today: '2026-10-21' })

    expect(await screen.findByText('Kohorta neobsahuje žádné případy')).toBeInTheDocument()
  })
})
