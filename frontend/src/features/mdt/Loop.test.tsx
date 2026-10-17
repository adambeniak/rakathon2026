import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http } from 'msw'
import { axe } from 'vitest-axe'
import { loopBody } from '@/features/mdt/api'
import { api } from '@/lib/api/http'
import { setDemo } from '@/lib/demo'
import type { Role } from '@/lib/domain'
import { problem } from '@/mocks/handlers/util'
import { DEMO_USERS } from '@/mocks/fixtures/people'
import { resetStore } from '@/mocks/fixtures/store'
import { server } from '@/mocks/server'
import { renderRoute } from '@/test/render'

const ID = 'rakathon-2026-prochazkova'
const MDT = `/cases/${ID}/mdt`
const TODAY = '2026-10-21'

/** Bodies of the transitions the screen sends (MSW lifecycle; the default handlers still answer). */
function recordBodies(): Array<Record<string, unknown>> {
  const bodies: Array<Record<string, unknown>> = []
  server.events.on('request:start', async ({ request }) => {
    if (request.method === 'POST' && new URL(request.url).pathname.endsWith('/transitions')) bodies.push((await request.clone().json()) as Record<string, unknown>)
  })
  return bodies
}
beforeEach(() => resetStore())
afterEach(() => server.events.removeAllListeners())

/** Test setup through the API as `role`, like another user did it earlier. */
async function asRole(role: Role, body: Record<string, unknown>) {
  setDemo({ role, today: TODAY })
  await api.post(`/api/cases/${ID}/transitions`, body)
}
const sign = (text = 'Závěr MDT dle zápisu.') => asRole('physician', { event: 'record_mdt_conclusion', conclusion: text })

describe('request body', () => {
  it('conclusion is trimmed and carries no signer; the other events carry only the event', () => {
    expect(loopBody({ event: 'record_mdt_conclusion', conclusion: '  Závěr  ' })).toEqual({ event: 'record_mdt_conclusion', conclusion: 'Závěr' })
    expect(loopBody({ event: 'send_feedback' })).toEqual({ event: 'send_feedback' })
    expect(loopBody({ event: 'close' })).toEqual({ event: 'close' })
  })
})

describe('Zapsat závěr MDT (Lékař KOC)', () => {
  it('shows the conclusion as saved only after the API signed it, read-only with signer and time', async () => {
    const bodies = recordBodies()
    const { container } = renderRoute(MDT, { role: 'physician', today: TODAY })
    const form = await screen.findByRole('form', { name: 'Zapsat závěr MDT' })
    expect(screen.queryByLabelText('Podepsaný závěr MDT')).not.toBeInTheDocument()
    await userEvent.type(within(form).getByLabelText('Text závěru MDT'), '  Doporučen další postup dle zápisu.  ')
    await userEvent.click(within(form).getByRole('button', { name: 'Zapsat závěr MDT' }))

    const signed = await screen.findByLabelText('Podepsaný závěr MDT')
    expect(signed).toHaveTextContent('Doporučen další postup dle zápisu.')
    expect(signed).toHaveTextContent(`Podepsal(a) ${DEMO_USERS.physician.name} · 21. 10. 2026 9:30`)
    expect(screen.queryByRole('form', { name: 'Zapsat závěr MDT' })).not.toBeInTheDocument()
    expect(bodies).toEqual([{ event: 'record_mdt_conclusion', conclusion: 'Doporučen další postup dle zápisu.' }])
    expect(await axe(container)).toHaveNoViolations()
  })

  it('a refused write is not shown as saved; the API words are shown', async () => {
    server.use(http.post('/api/cases/:id/transitions', () => problem(409, 'Přechod nelze provést')))
    renderRoute(MDT, { role: 'physician', today: TODAY })
    const form = await screen.findByRole('form', { name: 'Zapsat závěr MDT' })
    await userEvent.type(within(form).getByLabelText('Text závěru MDT'), 'Závěr')
    await userEvent.click(within(form).getByRole('button', { name: 'Zapsat závěr MDT' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Přechod nelze provést')
    expect(screen.queryByLabelText('Podepsaný závěr MDT')).not.toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Zapsat závěr MDT' })).toBeInTheDocument()
  })

  it('the state machine\'s generic "Conflict" is worded in Czech, with the guard detail', async () => {
    server.use(
      http.post('/api/cases/:id/transitions', () =>
        Response.json({ title: 'Conflict', status: 409, detail: "role 'coordinator' may not 'record_mdt_conclusion'" }, { status: 409, headers: { 'Content-Type': 'application/problem+json' } }),
      ),
    )
    renderRoute(MDT, { role: 'physician', today: TODAY })
    const form = await screen.findByRole('form', { name: 'Zapsat závěr MDT' })
    await userEvent.type(within(form).getByLabelText('Text závěru MDT'), 'Závěr')
    await userEvent.click(within(form).getByRole('button', { name: 'Zapsat závěr MDT' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("Událost nelze v tomto stavu případu nebo touto rolí provést. (role 'coordinator' may not 'record_mdt_conclusion')")
  })

  it('the coordinator sees no form, only the placeholder', async () => {
    renderRoute(MDT, { role: 'coordinator', today: TODAY })
    expect(await screen.findByText(/Doplní se po jednání MDT/)).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Zapsat závěr MDT' })).not.toBeInTheDocument()
  })

  it('an already signed conclusion is read-only for everyone in the KOC team', async () => {
    await sign('Podepsáno dříve.')
    renderRoute(MDT, { role: 'coordinator', today: TODAY, keepStore: true })
    expect(await screen.findByLabelText('Podepsaný závěr MDT')).toHaveTextContent('Podepsáno dříve.')
  })
})

describe('Odeslat závěr PL (koordinátorka)', () => {
  it('sends the feedback and shows it as handed over for delivery', async () => {
    await sign()
    const bodies = recordBodies()
    renderRoute(MDT, { role: 'coordinator', today: TODAY, keepStore: true })
    await userEvent.click(await screen.findByRole('button', { name: 'Odeslat závěr PL' }))
    expect(await screen.findByText('Závěr je předán k doručení praktickému lékaři.')).toBeInTheDocument()
    expect(bodies).toEqual([{ event: 'send_feedback' }])
    expect(screen.queryByRole('button', { name: 'Odeslat závěr PL' })).not.toBeInTheDocument()
  })

  it('on 503 shows a Czech retry message, changes nothing, and the same button tries again', async () => {
    await sign()
    server.use(http.post('/api/cases/:id/transitions', () => problem(503, 'mail-unavailable'), { once: true }))
    renderRoute(MDT, { role: 'coordinator', today: TODAY, keepStore: true })
    const send = await screen.findByRole('button', { name: 'Odeslat závěr PL' })
    await userEvent.click(send)
    expect(await screen.findByRole('alert')).toHaveTextContent('Zkuste to prosím za chvíli znovu')
    expect(screen.queryByText('Závěr je předán k doručení praktickému lékaři.')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Odeslat závěr PL' }))
    expect(await screen.findByText('Závěr je předán k doručení praktickému lékaři.')).toBeInTheDocument()
  })

  it('is not offered to the physician or while nothing is signed', async () => {
    renderRoute(MDT, { role: 'coordinator', today: TODAY })
    expect(await screen.findByText('Závěr MDT ještě nebyl zapsán lékařem KOC.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Odeslat závěr PL' })).not.toBeInTheDocument()
  })

  it('the physician has no loop actions', async () => {
    await sign()
    renderRoute(MDT, { role: 'physician', today: TODAY, keepStore: true })
    await screen.findByLabelText('Podepsaný závěr MDT')
    expect(screen.queryByRole('region', { name: 'Předání závěru a uzavření' })).not.toBeInTheDocument()
  })
})

describe('Uzavřít případ (koordinátorka)', () => {
  async function handedOver() {
    await sign()
    await asRole('coordinator', { event: 'send_feedback' })
  }

  it('warns that the GP read receipt is not known here, but allows closing', async () => {
    await handedOver()
    const bodies = recordBodies()
    renderRoute(MDT, { role: 'coordinator', today: TODAY, keepStore: true })
    await userEvent.click(await screen.findByRole('button', { name: 'Uzavřít případ' }))
    const warning = await screen.findByRole('group', { name: 'Uzavřít případ' })
    expect(warning).toHaveTextContent('Zda praktický lékař závěr otevřel, tato obrazovka nezjišťuje')
    await userEvent.click(within(warning).getByRole('button', { name: 'Uzavřít přesto' }))
    expect(await screen.findByText('Případ je uzavřen.')).toBeInTheDocument()
    expect(bodies).toEqual([{ event: 'close' }])
  })

  it('cancelling the warning closes nothing', async () => {
    await handedOver()
    renderRoute(MDT, { role: 'coordinator', today: TODAY, keepStore: true })
    await userEvent.click(await screen.findByRole('button', { name: 'Uzavřít případ' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Zrušit' }))
    expect(screen.queryByRole('group', { name: 'Uzavřít případ' })).not.toBeInTheDocument()
    expect(screen.queryByText('Případ je uzavřen.')).not.toBeInTheDocument()
  })

  it('shows the API problem when closing is refused', async () => {
    await handedOver()
    server.use(http.post('/api/cases/:id/transitions', () => problem(409, 'Doručení nebylo potvrzeno')))
    renderRoute(MDT, { role: 'coordinator', today: TODAY, keepStore: true })
    await userEvent.click(await screen.findByRole('button', { name: 'Uzavřít případ' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Uzavřít přesto' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Doručení nebylo potvrzeno')
    await waitFor(() => expect(screen.queryByText('Případ je uzavřen.')).not.toBeInTheDocument())
  })
})
