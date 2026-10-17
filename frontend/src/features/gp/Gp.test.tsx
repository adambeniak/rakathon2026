import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { problem } from '@/mocks/handlers/util'
import { server } from '@/mocks/server'
import { renderRoute } from '@/test/render'

const OPEN = /Otevřít závěr MDT: Ludmila Horáková/

/** Records the bodies POSTed to /transitions and the role header of the conclusion read. */
function spy() {
  const events: string[] = []
  const roles: (string | null)[] = []
  server.events.on('request:start', async ({ request }) => {
    const url = new URL(request.url)
    if (request.method === 'POST' && url.pathname.endsWith('/transitions')) {
      events.push(
        `${url.pathname.split('/')[3]}:${((await request.clone().json()) as { event: string }).event}`,
      )
    }
    if (url.pathname.endsWith('/mdt-conclusion')) roles.push(request.headers.get('x-demo-role'))
  })
  return { events, roles }
}

afterEach(() => server.events.removeAllListeners())

describe('GP portal, demo step 6', () => {
  it('records nothing until the GP opens the result; opening shows the signed conclusion, then the receipt', async () => {
    const { events, roles } = spy()
    renderRoute('/gp', { role: 'gp', today: '2026-10-21' })
    const open = await screen.findByRole('button', { name: OPEN })
    expect(events).toEqual([])
    expect(screen.getByText(/předáno k doručení/)).toBeInTheDocument() // relay accepted, not "doručeno"
    expect(screen.queryByText(/doručeno/i)).toBeNull()

    await userEvent.click(open)

    expect(
      await screen.findByText('Závěr MDT: postup dle zápisu z jednání ze dne 21. 10. 2026.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Podepsal\(a\) MUDr\. Lenka Marková dne 21\. 10\. 2026 9:30/),
    ).toBeInTheDocument()
    expect(
      await screen.findByText('Otevření závěru bylo zaznamenáno do auditní stopy.'),
    ).toBeInTheDocument()
    expect(roles).toEqual(['gp'])
    await waitFor(() => expect(events).toEqual(['c-horakova:gp_opened'])) // exactly once, for the opened case only
  })

  it('does not record a receipt when the conclusion cannot be read, and offers a retry', async () => {
    const { events } = spy()
    server.use(
      http.get('/api/cases/:id/mdt-conclusion', () =>
        problem(403, 'Zpětná vazba ještě nebyla odeslána'),
      ),
    )
    renderRoute('/gp', { role: 'gp', today: '2026-10-21' })

    await userEvent.click(await screen.findByRole('button', { name: OPEN }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(events).toEqual([])
    expect(screen.getByRole('button', { name: 'Zkusit znovu' })).toBeInTheDocument()
  })

  it('shows the conclusion even when the receipt fails, says so and records on retry', async () => {
    let fail = true
    server.use(
      http.post('/api/cases/:id/transitions', () =>
        fail
          ? problem(409, 'Zpětná vazba není ve stavu k otevření')
          : HttpResponse.json({ id: 'c-horakova', state: 'zpetna_vazba_odeslana' }),
      ),
    )
    renderRoute('/gp', { role: 'gp', today: '2026-10-21' })

    await userEvent.click(await screen.findByRole('button', { name: OPEN }))

    expect(await screen.findByText(/Závěr MDT: postup/)).toBeInTheDocument()
    expect(
      await screen.findByText(/Otevření závěru se nepodařilo zaznamenat\./),
    ).toBeInTheDocument()
    fail = false
    await userEvent.click(screen.getByRole('button', { name: 'Zkusit znovu' }))
    expect(
      await screen.findByText('Otevření závěru bylo zaznamenáno do auditní stopy.'),
    ).toBeInTheDocument()
  })

  it('lists cases from GET /api/cases, with "—" for counts the backend has not computed', async () => {
    server.use(
      http.get('/api/cases', () =>
        HttpResponse.json([
          {
            id: 'x',
            patient: {
              display_name: 'Test Pacient',
              birth_date: '1970-01-01',
              age_years: 56,
              sex: 'unknown',
            },
            state: 'kompletni',
            bucket: 'aktivni',
            postponed: false,
            document_count: 3,
          },
        ]),
      ),
    )
    renderRoute('/gp', { role: 'gp', today: '2026-10-21' })

    expect(await screen.findByRole('link', { name: 'Test Pacient' })).toBeInTheDocument()
    expect(screen.queryByText('Nic nechybí')).toBeNull() // unknown is not "nothing missing"
    expect(screen.queryByRole('button', { name: /Otevřít závěr MDT/ })).toBeNull()
  })
})
