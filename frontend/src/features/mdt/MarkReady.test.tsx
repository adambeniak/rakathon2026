import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http } from 'msw'
import { axe } from 'vitest-axe'
import { blockingItems, loopBody } from '@/features/mdt/api'
import { ApiProblem } from '@/lib/api/problem'
import { resetStore } from '@/mocks/fixtures/store'
import { problem } from '@/mocks/handlers/util'
import { server } from '@/mocks/server'
import { renderRoute } from '@/test/render'

const MDT = '/cases/rakathon-2026-prochazkova/mdt'
const TODAY = '2026-10-20' // the demo case is `kompletni` before the MDT day

function recordBodies(): Array<Record<string, unknown>> {
  const bodies: Array<Record<string, unknown>> = []
  server.events.on('request:start', async ({ request }) => {
    if (request.method === 'POST' && new URL(request.url).pathname.endsWith('/transitions'))
      bodies.push((await request.clone().json()) as Record<string, unknown>)
  })
  return bodies
}
beforeEach(() => resetStore())
afterEach(() => server.events.removeAllListeners())

describe('request body and gate parsing', () => {
  it('mark_ready_mdt sends the event, and waivers only when given; readiness is never sent', () => {
    expect(loopBody({ event: 'mark_ready_mdt' })).toEqual({ event: 'mark_ready_mdt' })
    expect(loopBody({ event: 'mark_ready_mdt', waivers: [] })).toEqual({ event: 'mark_ready_mdt' })
    const body = loopBody({
      event: 'mark_ready_mdt',
      waivers: [{ item: 'performance_status', reason: '  PS doplní lékař  ' }],
    })
    expect(body).toEqual({
      event: 'mark_ready_mdt',
      waivers: [{ item: 'performance_status', reason: 'PS doplní lékař' }],
    })
    expect(body).not.toHaveProperty('readiness')
  })

  it('reads the blocking items from blocking_items of a 409 guard_failed, never from the detail sentence', () => {
    const title = 'Podmínky akce nejsou splněny'
    const sentence = 'Připravenost k MDT není splněna, chybí: performance_status, ct_staging'
    expect(
      blockingItems(
        new ApiProblem(409, title, sentence, 'guard_failed', ['performance_status', 'ct_staging']),
      ),
    ).toEqual(['performance_status', 'ct_staging'])
    // The sentence alone no longer opens the waiver form (a rewording cannot break it).
    expect(blockingItems(new ApiProblem(409, title, sentence, 'guard_failed'))).toBeNull()
    expect(blockingItems(new ApiProblem(409, title, sentence))).toBeNull()
    // A guard that names no item (readiness check missing) and an empty list give no form either.
    expect(
      blockingItems(
        new ApiProblem(409, title, 'Chybí výsledek kontroly připravenosti k MDT', 'guard_failed'),
      ),
    ).toBeNull()
    expect(blockingItems(new ApiProblem(409, title, sentence, 'guard_failed', []))).toBeNull()
    expect(
      blockingItems(
        new ApiProblem(409, 'Akce není v tomto stavu povolena', 'x', 'invalid_transition', [
          'histology',
        ]),
      ),
    ).toBeNull()
    expect(
      blockingItems(
        new ApiProblem(403, 'Přístup byl odepřen', 'x', 'forbidden_role', ['histology']),
      ),
    ).toBeNull()
    expect(blockingItems(new Error('x'))).toBeNull()
  })
})

describe('Označit jako připravený k MDT (Lékař KOC)', () => {
  it('shows the items the server blocks on, waives them with a reason and retries', async () => {
    const bodies = recordBodies()
    const { container } = renderRoute(MDT, { role: 'physician', today: TODAY })
    await userEvent.click(
      await screen.findByRole('button', { name: 'Označit jako připravený k MDT' }),
    )

    const form = await screen.findByRole('form', { name: 'Prominout a označit jako připravený' })
    expect(within(form).getByText('Server vrátil chybějící položky:')).toBeInTheDocument()
    const submit = within(form).getByRole('button', { name: 'Prominout a označit jako připravený' })
    expect(submit).toBeDisabled() // no reason yet
    await userEvent.type(
      within(form).getByLabelText('Důvod prominutí: Stav výkonnosti (PS/ECOG)'),
      'PS doplní lékař na jednání.',
    )
    expect(await axe(container)).toHaveNoViolations()
    await userEvent.click(submit)

    expect(await screen.findByText('Případ je označen jako připravený k MDT.')).toBeInTheDocument()
    expect(bodies).toEqual([
      { event: 'mark_ready_mdt' },
      {
        event: 'mark_ready_mdt',
        waivers: [{ item: 'performance_status', reason: 'PS doplní lékař na jednání.' }],
      },
    ])
  })

  it('cancelling the waiver form sends nothing more and offers the button again', async () => {
    const bodies = recordBodies()
    renderRoute(MDT, { role: 'physician', today: TODAY })
    await userEvent.click(
      await screen.findByRole('button', { name: 'Označit jako připravený k MDT' }),
    )
    await userEvent.click(await screen.findByRole('button', { name: 'Zrušit' }))
    expect(
      screen.queryByRole('form', { name: 'Prominout a označit jako připravený' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Označit jako připravený k MDT' })).toBeEnabled()
    expect(bodies).toHaveLength(1)
  })

  it('any other refusal is shown as text, without a waiver form', async () => {
    server.use(
      http.post('/api/cases/:id/transitions', () =>
        problem(409, 'Handover pro MDT ještě nebyl sestaven'),
      ),
    )
    renderRoute(MDT, { role: 'physician', today: TODAY })
    await userEvent.click(
      await screen.findByRole('button', { name: 'Označit jako připravený k MDT' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Handover pro MDT ještě nebyl sestaven',
    )
    expect(
      screen.queryByRole('form', { name: 'Prominout a označit jako připravený' }),
    ).not.toBeInTheDocument()
  })

  it('is offered to the physician only, and only while the case is kompletni', async () => {
    renderRoute(MDT, { role: 'coordinator', today: TODAY })
    await screen.findByRole('region', { name: 'Stav handoveru k MDT' })
    expect(
      screen.queryByRole('button', { name: 'Označit jako připravený k MDT' }),
    ).not.toBeInTheDocument()
  })

  it('is not offered once the case is ready (MDT day)', async () => {
    renderRoute(MDT, { role: 'physician', today: '2026-10-21' })
    await screen.findByRole('form', { name: 'Zapsat závěr MDT' })
    expect(
      screen.queryByRole('button', { name: 'Označit jako připravený k MDT' }),
    ).not.toBeInTheDocument()
  })
})
