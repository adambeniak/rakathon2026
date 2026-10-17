// MOCK copy – the reports the GP's letter (07) lists and the coordinator requests in triage (demo step 2).

export const LETTER = '07_PL_zadost_KOC2_2026-10-02'

// The five reports the GP's letter lists (numbered lines of report 07), in the backend's order; the GP's own epicrisis
// (04) is not among them. The evidence quote is the verbatim numbered line, `label` the same without its number.
export const LISTED = [
  {
    doc: '02_Laborator_2026-09-01',
    exam: '2026-09-01',
    org: 'labjih',
    recipient: 'Laboratoř LabJih',
    by: 'organization',
    label:
      'Laboratorní vyšetření 1. 9. 2026 – krevní obraz, biochemie, moč chemicky a sediment, kultivace moči (LabJih)',
  },
  {
    doc: '03_RTG_plic_2026-09-03',
    exam: '2026-09-03',
    org: 'rc-modrany',
    recipient: 'Radiologické centrum Modřany',
    by: 'organization',
    label: 'RTG plic 3. 9. 2026 (Radiologické centrum Modřany)',
  },
  {
    doc: '05_Gastroenterologie_2026-09-15',
    exam: '2026-09-15',
    org: 'poliklinika-jizni',
    recipient: 'Poliklinika Jižní',
    by: 'organization',
    label: 'Gastroenterologické vyšetření 15. 9. 2026 (MUDr. Ivana Křížová, Poliklinika Jižní)',
  },
  {
    doc: '06_UZ_bricha_2026-09-29',
    exam: '2026-09-29',
    org: 'poliklinika-jizni',
    recipient: 'Poliklinika Jižní',
    by: 'organization',
    label: 'UZ břicha 29. 9. 2026 (RDG pracoviště, Poliklinika Jižní)',
  },
  {
    doc: '01_Kardiologie_2026-07-20',
    exam: '2026-07-20',
    org: 'kardio-jesenice',
    recipient: 'Kardiologická ambulance Jesenice',
    by: 'practitioner',
    label: 'Kardiologická kontrola 20. 7. 2026 (MUDr. Petr Malý)',
  },
] as const

export const requestId = (doc: string) => `req-${doc}`

/** When the mock coordinator sent the requests (2. 10., right after taking the case over). */
export const REQUESTED_AT = '2026-10-02T11:30:00+02:00'
