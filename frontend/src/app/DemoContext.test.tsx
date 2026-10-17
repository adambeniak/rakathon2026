import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setDemo } from '@/lib/demo'
import { problem } from '@/mocks/handlers/util'
import { server } from '@/mocks/server'
import { DemoProvider, useDemo } from './DemoContext'

function Probe() {
  const { today, setToday } = useDemo()
  return (
    <>
      <p data-testid="today">{today}</p>
      <button type="button" onClick={() => setToday('2026-10-19')}>
        move
      </button>
    </>
  )
}

const mount = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DemoProvider>
        <Probe />
      </DemoProvider>
    </QueryClientProvider>,
  )

describe('DemoProvider against the real backend', () => {
  beforeEach(() => {
    vi.stubEnv('MODE', 'development') // isMocked() = false: the backend clock rules
    setDemo({ role: 'coordinator', today: '2026-10-02' })
  })
  afterEach(() => vi.unstubAllEnvs())

  it('adopts the date of the backend clock on load', async () => {
    server.use(http.get('/api/demo/clock', () => HttpResponse.json({ now: '2026-10-16T09:00:00+02:00', overridden: true })))
    mount()
    await waitFor(() => expect(screen.getByTestId('today')).toHaveTextContent('2026-10-16'))
  })

  it('moves the backend clock when the date is switched', async () => {
    let put: unknown
    server.use(
      http.get('/api/demo/clock', () => HttpResponse.json({ now: '2026-10-02T09:00:00+02:00', overridden: false })),
      http.put('/api/demo/clock', async ({ request }) => {
        put = await request.json()
        return HttpResponse.json({ now: '2026-10-19T09:00:00+02:00', overridden: true })
      }),
    )
    mount()
    await userEvent.click(screen.getByRole('button', { name: 'move' }))
    await waitFor(() => expect(screen.getByTestId('today')).toHaveTextContent('2026-10-19'))
    expect(put).toEqual({ now: '2026-10-19T09:00:00+02:00' })
  })

  it('keeps the date and shows the problem when the clock cannot be moved', async () => {
    server.use(
      http.get('/api/demo/clock', () => HttpResponse.json({ now: '2026-10-02T09:00:00+02:00', overridden: false })),
      http.put('/api/demo/clock', () => problem(404, 'Demo hodiny nejsou dostupné')),
    )
    mount()
    await userEvent.click(screen.getByRole('button', { name: 'move' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Demo hodiny nejsou dostupné')
    expect(screen.getByTestId('today')).toHaveTextContent('2026-10-02')
  })
})

describe('DemoProvider with mocks', () => {
  it('only changes the date locally and never calls the clock endpoint', async () => {
    setDemo({ role: 'coordinator', today: '2026-10-02' })
    const calls: string[] = []
    server.events.on('request:start', ({ request }) => calls.push(new URL(request.url).pathname))
    mount()
    await userEvent.click(screen.getByRole('button', { name: 'move' }))
    expect(screen.getByTestId('today')).toHaveTextContent('2026-10-19')
    expect(calls.filter((c) => c.includes('/demo/clock'))).toEqual([])
    server.events.removeAllListeners()
  })
})
