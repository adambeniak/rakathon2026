import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { vi } from 'vitest'
import { client } from '@/lib/api/client'
import { ALENA_ID } from '@/mocks/fixtures/cases'
import { server } from '@/mocks/server'
import { renderRoute } from '@/test/render'
import { eventLabel, timelineItem } from './activity'
import type { TimelineEntry } from './schemas'

const CASE = `/cases/${ALENA_ID}`

describe('case activity tabs (audit, timeline, messages)', () => {
  it('timeline: merged events in Czech, with the MDT start and the backend after-MDT flag', async () => {
    renderRoute(`${CASE}/timeline`, { role: 'coordinator', today: '2026-10-26' })
    const section = await screen.findByRole('region', { name: 'Časová osa' })
    expect(
      await within(section).findByText('Podklady k MDT: stav k 21. 10. 2026 8:00'),
    ).toBeInTheDocument()
    expect(within(section).getByText('Jednání MDT')).toBeInTheDocument()
    expect(within(section).getByText('Případ převzat koordinátorkou')).toBeInTheDocument()
    expect(within(section).getByText('Odesláno → V triage')).toBeInTheDocument()
    const late = within(section)
      .getByText(/Přijat dokument: Algeziologické vyšetření/)
      .closest('li')!
    expect(within(late).getByText('Po MDT – mimo podklady k MDT')).toBeInTheDocument()
    expect(within(late).getByText('26. 10. 2026 12:00')).toBeInTheDocument()
    const histology = within(section)
      .getByText(/Přijat dokument: Histologie/)
      .closest('li')!
    expect(within(histology).queryByText('Po MDT – mimo podklady k MDT')).not.toBeInTheDocument()
    // the authored date is a day only
    expect(within(section).getAllByText('26. 10. 2026').length).toBeGreaterThan(0)
  })

  it('messages: requests to workplaces with their state, no feedback before it is sent', async () => {
    renderRoute(`${CASE}/messages`, { role: 'coordinator', today: '2026-10-16' })
    const section = await screen.findByRole('region', { name: 'Komunikace' })
    const cards = await within(section).findAllByText('Žádost o zaslání výsledku')
    expect(cards).toHaveLength(5)
    expect(within(section).getAllByText('Výsledek doručen')).toHaveLength(5) // 01–06 arrived on 8. 10.
    expect(
      within(section).getByText(/RTG plic 3\. 9\. 2026 \(Radiologické centrum Modřany\)/),
    ).toBeInTheDocument()
    expect(within(section).queryByText('Zpětná vazba z MDT (e-mail)')).not.toBeInTheDocument()
  })

  it('audit: newest first, who with role, the action named in Czech, through the contract path', async () => {
    const get = vi.spyOn(client, 'GET')
    renderRoute(`${CASE}/audit`, { role: 'physician', today: '2026-10-21' })
    const table = await screen.findByRole('table')
    const rows = within(table).getAllByRole('row').slice(1)
    expect(within(rows[0]!).getByText('Označeno jako připravené k MDT')).toBeInTheDocument()
    expect(
      within(rows[0]!).getByText('doc. MUDr. Pavel Hrubý, Ph.D. (lékař KOC)'),
    ).toBeInTheDocument()
    expect(within(table).getAllByText('Štafeta (systém)').length).toBeGreaterThan(0) // the system actor, no role suffix
    expect(within(table).getAllByText('dokument, případ / úkol').length).toBeGreaterThan(0)
    expect(get).toHaveBeenCalledWith('/api/cases/{case_id}/audit', {
      params: { path: { case_id: ALENA_ID }, query: { limit: 100 } },
    })
    get.mockRestore()
  })

  it('a response that does not match the contract shows the error state, not half a list', async () => {
    server.use(
      http.get('/api/cases/:id/audit', () =>
        HttpResponse.json([{ at: '2026-10-02', who: 'x', action: 'y' }]),
      ),
    )
    renderRoute(`${CASE}/audit`, { role: 'coordinator', today: '2026-10-21' })
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})

describe('activity labels', () => {
  const entry: TimelineEntry = {
    id: 'x',
    kind: 'document_received',
    at: '2026-10-19T12:00:00+02:00',
    date_only: false,
    planned: false,
    title: 'Histologie',
    excluded_from_handover: null,
  }

  it('does not flag a document when the API could not compare it with an MDT start (null)', () => {
    expect(timelineItem(entry).excluded).toBe(false)
    expect(timelineItem({ ...entry, excluded_from_handover: true }).excluded).toBe(true)
  })

  it('names an unknown workflow event by its code instead of guessing', () => {
    expect(eventLabel('accept')).toBe('Případ převzat koordinátorkou')
    expect(eventLabel('something_new')).toBe('Událost případu (something_new)')
  })
})
