import { daysUntil, formatDate, formatDateTime, formatRemaining } from './date'

describe('date helpers', () => {
  it('formats Czech dates', () => {
    expect(formatDate('2026-10-21')).toBe('21. 10. 2026')
    expect(formatDate('2026-10-02')).toBe('2. 10. 2026')
  })
  it('uses Prague time for timestamps', () => {
    expect(formatDate('2026-10-20T22:30:00Z')).toBe('21. 10. 2026')
    expect(formatDateTime('2026-10-21T08:00:00+02:00')).toBe('21. 10. 2026 8:00')
  })
  it('counts days and phrases them in Czech', () => {
    expect(daysUntil('2026-10-21', '2026-10-16')).toBe(5)
    expect(formatRemaining(5)).toBe('za 5 dní')
    expect(formatRemaining(2)).toBe('za 2 dny')
    expect(formatRemaining(-1)).toBe('po termínu 1 den')
    expect(formatRemaining(0)).toBe('dnes')
  })
})

import { isoToPragueLocal, pragueLocalToIso } from './date'

describe('prague wall-clock conversion', () => {
  it('round-trips the MDT as-of', () => {
    expect(pragueLocalToIso('2026-10-21T08:00')).toBe('2026-10-21T08:00:00+02:00')
    expect(isoToPragueLocal('2026-10-21T08:00:00+02:00')).toBe('2026-10-21T08:00')
  })
  it('uses winter offset after the DST change', () => {
    expect(pragueLocalToIso('2026-10-26T08:00')).toBe('2026-10-26T08:00:00+01:00')
  })
})
