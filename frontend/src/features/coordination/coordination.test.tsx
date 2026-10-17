import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { axe } from 'vitest-axe'
import { launchBody, transitionBody, DEMO_MDT_START_LOCAL, KOC_PHYSICIANS } from '@/features/coordination/api'
import { problem } from '@/mocks/handlers/util'
import { server } from '@/mocks/server'
import { renderRoute } from '@/test/render'

const ALENA = '/cases/rakathon-2026-prochazkova'
const TASKS = `${ALENA}/tasks`

/** Bodies of the requests the UI sends, recorded from the MSW lifecycle (the default handlers still answer). */
function recordBodies(method: string, pathPart: string): unknown[] {
  const bodies: unknown[] = []
  server.events.on('request:start', async ({ request }) => {
    if (request.method === method && new URL(request.url).pathname.includes(pathPart)) bodies.push(await request.clone().json())
  })
  return bodies
}
afterEach(() => server.events.removeAllListeners())

describe('request bodies', () => {
  it('launch carries the indicating physician, the MDT start with the Prague offset and the plan url', () => {
    expect(launchBody({ startDate: '2026-10-02', indicatedBy: 'hruby-pavel@koc2-nemocnice-lipova', mdtStartLocal: DEMO_MDT_START_LOCAL })).toEqual({
      plan_url: 'https://stafeta.example/fhir/PlanDefinition/pancreas-dx',
      start_date: '2026-10-02',
      indicated_by: 'hruby-pavel@koc2-nemocnice-lipova',
      mdt_start: '2026-10-21T08:00:00+02:00',
    })
  })

  it('confirm sends place and date, perform nothing else, deliver the result document', () => {
    expect(transitionBody({ taskId: 'x', event: 'confirm', place: 'KOC 1 – radiologie', date: '2026-10-08' })).toEqual({
      event: 'confirm',
      place: 'KOC 1 – radiologie',
      date: '2026-10-08',
    })
    expect(transitionBody({ taskId: 'x', event: 'perform' })).toEqual({ event: 'perform' })
    expect(transitionBody({ taskId: 'x', event: 'deliver_result', documentId: '11_Histologie' })).toEqual({
      event: 'deliver_result',
      document_id: '11_Histologie',
    })
  })
})

describe('pathway launch', () => {
  it('is offered while the case has no steps and sends the form values', async () => {
    const bodies = recordBodies('POST', '/pathways')
    renderRoute(TASKS, { today: '2026-10-02' })
    expect(await screen.findByText('Žádné úkoly')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Spustit sadu: Karcinom pankreatu – diagnostika' }))

    const form = await screen.findByRole('form', { name: 'Spustit sadu: Karcinom pankreatu – diagnostika' })
    // Pre-filled: the seeded physician, the demo date and the MDT start 21. 10. 2026 8:00.
    expect(within(form).getByLabelText('Indikující lékař KOC')).toHaveValue(KOC_PHYSICIANS[0]?.id)
    expect(within(form).getByLabelText('Začátek sady')).toHaveValue('2026-10-02')
    expect(within(form).getByLabelText('Plánovaný začátek MDT')).toHaveValue(DEMO_MDT_START_LOCAL)
    await userEvent.click(within(form).getByRole('button', { name: 'Spustit sadu' }))

    const board = await screen.findByRole('group', { name: 'Kdo je na tahu' })
    expect(bodies).toEqual([
      {
        plan_url: 'https://stafeta.example/fhir/PlanDefinition/pancreas-dx',
        start_date: '2026-10-02',
        indicated_by: KOC_PHYSICIANS[0]?.id,
        mdt_start: '2026-10-21T08:00:00+02:00',
      },
    ])
    // Lanes are the backend roles.
    for (const lane of ['PL', 'Koordinátor', 'Lékař KOC', 'Externí pracoviště', 'Pacient']) {
      expect(within(board).getByRole('heading', { name: lane })).toBeInTheDocument()
    }
    // Nothing is ordered yet: the coordinator keeps the baton and has to confirm the order.
    const tab = within(screen.getByRole('region', { name: 'Úkoly' }))
    expect(tab.getByText(/Na tahu:/)).toBeInTheDocument()
    expect(tab.getByText(/^Potvrdit objednání: /)).toBeInTheDocument()
    expect(within(board).getAllByText(/^Čeká na:/).length).toBeGreaterThan(0)
  })

  it('shows the API problem title when the launch is refused', async () => {
    server.use(http.post('/api/cases/:id/pathways', () => problem(422, 'Sada vyšetření vyžaduje indikujícího lékaře KOC.')))
    renderRoute(TASKS, { today: '2026-10-02' })
    await userEvent.click(await screen.findByRole('button', { name: /^Spustit sadu/ }))
    await userEvent.click(await screen.findByRole('button', { name: 'Spustit sadu' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Sada vyšetření vyžaduje indikujícího lékaře KOC.')
  })

  it('is disabled for roles other than the coordinator', async () => {
    renderRoute(TASKS, { today: '2026-10-02', role: 'physician' })
    expect(await screen.findByRole('button', { name: /^Spustit sadu/ })).toBeDisabled()
  })
})

describe('board', () => {
  it('renders the overdue and escalation flags the API sends (histology, 16. 10.)', async () => {
    const { container } = renderRoute(TASKS, { today: '2026-10-16' })
    const hist = (await screen.findByText('Histologie')).closest('li')
    if (!hist) throw new Error('histology card not found')
    expect(within(hist).getByText('Po termínu 1 pracovní den')).toBeInTheDocument()
    expect(within(hist).getByText('Eskalováno 16. 10. 2026')).toBeInTheDocument()
    expect(within(hist).getByText(/Slíbeno do 15\. 10\. 2026/)).toBeInTheDocument()
    expect(within(hist).getByText(/Termín 19\. 10\. 2026/)).toBeInTheDocument()
    // The baton is the histology, and it is flagged by the API's overdue flag.
    const tab = within(screen.getByRole('region', { name: 'Úkoly' }))
    const baton = tab.getByText(/Na tahu:/).closest('div')
    expect(baton).toHaveTextContent('Potvrdit objednání: Histologie')
    // Counted from the earlier of due and SLA, like the API's overdue flag.
    expect(baton).toHaveTextContent('do 15. 10. 2026 (po termínu 1 den)')
    expect(await axe(container)).toHaveNoViolations()
  })

  it('shows no flags before the deadline (15. 10.)', async () => {
    renderRoute(TASKS, { today: '2026-10-15' })
    const hist = (await screen.findByText('Histologie')).closest('li')
    if (!hist) throw new Error('histology card not found')
    expect(within(hist).queryByText(/^Po termínu/)).not.toBeInTheDocument()
    expect(within(hist).queryByText(/^Eskalováno/)).not.toBeInTheDocument()
  })
})

describe('task transitions', () => {
  it('confirm needs place and date, then perform and deliver_result with a document', async () => {
    const bodies = recordBodies('POST', '/transitions')
    renderRoute(TASKS, { today: '2026-10-16' })

    // Potvrdit objednání → form asks for place + date.
    await userEvent.click(await screen.findByRole('button', { name: 'Potvrdit objednání: Histologie' }))
    const confirm = await screen.findByRole('form', { name: 'Potvrdit objednání: Histologie' })
    const submit = within(confirm).getByRole('button', { name: 'Potvrdit' })
    expect(submit).toBeDisabled() // no date yet
    await userEvent.clear(within(confirm).getByLabelText('Pracoviště'))
    await userEvent.type(within(confirm).getByLabelText('Pracoviště'), 'KOC 2 – patologie')
    fireEvent.change(within(confirm).getByLabelText('Datum vyšetření'), { target: { value: '2026-10-19' } })
    await userEvent.click(submit)
    expect(await screen.findByRole('button', { name: 'Provedeno: Histologie' })).toBeEnabled()
    expect(bodies[0]).toEqual({ event: 'confirm', place: 'KOC 2 – patologie', date: '2026-10-19' })

    // Provedeno → perform.
    await userEvent.click(screen.getByRole('button', { name: 'Provedeno: Histologie' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Výsledek doručen: Histologie' }))
    expect(bodies[1]).toEqual({ event: 'perform' })

    // Výsledek doručen → result document is required.
    const deliver = await screen.findByRole('form', { name: 'Výsledek doručen: Histologie' })
    expect(within(deliver).getByRole('button', { name: 'Potvrdit doručení' })).toBeDisabled()
    const select = within(deliver).getByLabelText('Dokument s výsledkem')
    await waitFor(() => expect(within(select).getAllByRole('option').length).toBeGreaterThan(1))
    const first = within(select).getAllByRole('option')[1]
    await userEvent.selectOptions(select, first as HTMLOptionElement)
    await userEvent.click(within(deliver).getByRole('button', { name: 'Potvrdit doručení' }))
    await waitFor(() => expect(bodies).toHaveLength(3))
    expect(bodies[2]).toEqual({ event: 'deliver_result', document_id: (first as HTMLOptionElement).value })
    // The dependent step is no longer blocked.
    await waitFor(() => expect(screen.queryByText(/^Čeká na: Histologie/)).not.toBeInTheDocument())
  })

  it('a step with an unfinished prerequisite cannot be ordered', async () => {
    renderRoute(TASKS, { today: '2026-10-16' })
    const verify = await screen.findByRole('button', { name: /^Potvrdit objednání: Ověřit rozpor/ })
    expect(verify).toBeDisabled()
    expect(screen.getByText('Čeká na: Histologie')).toBeInTheDocument()
  })

  it('shows the API problem title when a transition is refused', async () => {
    server.use(http.post('/api/tasks/:taskId/transitions', () => problem(409, 'Přechod není povolen')))
    renderRoute(TASKS, { today: '2026-10-16' })
    await userEvent.click(await screen.findByRole('button', { name: 'Potvrdit objednání: Histologie' }))
    const confirm = await screen.findByRole('form', { name: 'Potvrdit objednání: Histologie' })
    await userEvent.type(within(confirm).getByLabelText('Pracoviště'), 'KOC 2 – patologie')
    fireEvent.change(within(confirm).getByLabelText('Datum vyšetření'), { target: { value: '2026-10-19' } })
    await userEvent.click(within(confirm).getByRole('button', { name: 'Potvrdit' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Přechod není povolen')
  })

  it('actions are disabled for roles other than the coordinator', async () => {
    renderRoute(TASKS, { today: '2026-10-16', role: 'physician' })
    expect(await screen.findByRole('button', { name: 'Potvrdit objednání: Histologie' })).toBeDisabled()
  })
})

describe('contract failure', () => {
  it('an unexpected board shape becomes an error state, not a crash', async () => {
    server.use(http.get('/api/cases/:id/board', () => HttpResponse.json({ lanes: 'nope' })))
    renderRoute(TASKS, { today: '2026-10-16' })
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
