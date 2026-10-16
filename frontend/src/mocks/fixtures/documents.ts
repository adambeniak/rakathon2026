import type { DocumentInfo } from '@/lib/domain'

// Titles and places come from the golden file (examinations); received dates are fictitious demo values.
const RAW: Array<[string, string, string, string, string]> = [
  ['01_Kardiologie_2026-07-20', 'Kardiologická kontrola', 'Kardiologická ambulance Jesenice', '2026-07-20', '2026-10-08T09:00:00+02:00'],
  ['02_Laborator_2026-09-01', 'Laboratorní vyšetření', 'Laboratoř LabJih', '2026-09-01', '2026-10-08T09:00:00+02:00'],
  ['03_RTG_plic_2026-09-03', 'RTG hrudníku PA', 'Radiologické centrum Modřany', '2026-09-03', '2026-10-08T09:00:00+02:00'],
  ['04_PL_epikriza_2026-09-04', 'Epikríza praktického lékaře', 'Ordinace PL MUDr. Řezníček', '2026-09-04', '2026-10-08T09:00:00+02:00'],
  ['05_Gastroenterologie_2026-09-15', 'Gastroenterologické vyšetření', 'Poliklinika Jižní – gastroenterologie', '2026-09-15', '2026-10-08T09:00:00+02:00'],
  ['06_UZ_bricha_2026-09-29', 'UZ břicha', 'Poliklinika Jižní – RDG', '2026-09-29', '2026-10-08T09:00:00+02:00'],
  ['07_PL_zadost_KOC2_2026-10-02', 'Žádost PL o převzetí do KOC 2', 'Ordinace PL MUDr. Řezníček', '2026-10-02', '2026-10-02T10:00:00+02:00'],
  ['08_CT_KOC1_2026-10-08', 'CT hrudníku a břicha', 'KOC 1 – Nemocnice Severní, radiologie', '2026-10-08', '2026-10-08T15:00:00+02:00'],
  ['09_Biopsie_vykon_KOC2_2026-10-12', 'Protokol EUS-FNB', 'KOC 2 – Nemocnice Lipová, endoskopie', '2026-10-12', '2026-10-12T14:00:00+02:00'],
  ['10_Laborator_KOC2_2026-10-15', 'Laboratoř vč. nádorových markerů', 'KOC 2 – Nemocnice Lipová, laboratoř', '2026-10-15', '2026-10-15T16:00:00+02:00'],
  ['11_Histologie_KOC2_2026-10-19', 'Histologie', 'KOC 2 – Nemocnice Lipová, patologie', '2026-10-19', '2026-10-19T12:00:00+02:00'],
  ['12_Algeziologie_2026-10-26', 'Algeziologické vyšetření', 'KOC 2 – Nemocnice Lipová, algeziologie', '2026-10-26', '2026-10-26T12:00:00+01:00'],
  ['13_Psychologie_KOC2_2026-10-27', 'Psychologické vyšetření', 'KOC 2 – Nemocnice Lipová, psychologie', '2026-10-27', '2026-10-27T12:00:00+01:00'],
]

export const AS_OF_DEFAULT = '2026-10-21T08:00:00+02:00'

export const DOCUMENTS: DocumentInfo[] = RAW.map(([id, title, place, authored, received]) => ({
  id,
  title,
  place,
  authored,
  received,
  afterAsOf: new Date(received).getTime() > new Date(AS_OF_DEFAULT).getTime(),
}))

export function documentById(id: string): DocumentInfo | undefined {
  return DOCUMENTS.find((d) => d.id === id)
}
