import { screen, within } from '@testing-library/react'
import { resetStore, store } from '@/mocks/fixtures/store'
import { renderRoute } from '@/test/render'

const ALENA = 'Alena Procházková'

/** The case after „Odeslat závěr PL“ (demo step 6.2): the conclusion is out, the case is not closed yet. */
function feedbackSent() {
  resetStore()
  store.markedReady = true
  store.conclusion = {
    text: 'Fiktivní závěr MDT.',
    by: 'MUDr. Test',
    signedAt: '2026-10-21T09:30:00+02:00',
  }
  store.feedbackSent = true
}

describe('coordinator inbox', () => {
  it('keeps a case whose feedback was sent in the Aktivní column, with a link to the case (#174)', async () => {
    feedbackSent()
    renderRoute('/inbox', { role: 'coordinator', today: '2026-10-21', keepStore: true })
    const active = await screen.findByRole('region', { name: /Aktivní/ })
    const card = await within(active).findByRole('article', { name: ALENA })
    expect(within(card).getByText('Zpětná vazba odeslána')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: ALENA })).toHaveAttribute(
      'href',
      '/cases/rakathon-2026-prochazkova',
    )
    // The other case waiting for the GP's read is listed too.
    expect(within(active).getByRole('article', { name: 'Ludmila Horáková' })).toBeInTheDocument()
  })

  it('archives the case once it is closed', async () => {
    feedbackSent()
    store.closed = true
    renderRoute('/inbox', { role: 'coordinator', today: '2026-10-21', keepStore: true })
    const active = await screen.findByRole('region', { name: /Aktivní/ })
    await within(active).findByRole('article', { name: 'Ludmila Horáková' })
    expect(screen.queryByRole('article', { name: ALENA })).toBeNull()
  })
})
