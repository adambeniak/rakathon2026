import { nextDeadline } from './tasks'

describe('nextDeadline', () => {
  it('moves on to the next task once the recorded phase completes the current one', () => {
    // Histology is due 15. 10. and not done by date on 16. 10.; it is the overdue case deadline.
    expect(nextDeadline('2026-10-16')).toMatchObject({ title: 'Histologie', due: '2026-10-15' })
    // Delivering its result on the board must clear that deadline from the case header and the inbox, too.
    expect(nextDeadline('2026-10-16', { 't-hist': 'result_delivered' })).toMatchObject({
      title: 'Ověřit rozpor v datech (apixaban, datum odběru)',
      due: '2026-10-21',
    })
  })
})
