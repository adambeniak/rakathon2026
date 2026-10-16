import type { Finding } from '@/lib/domain'
import { golden } from './golden'

// Czech copy is neutral ("v dokumentaci uvedeno…", "nesoulad mezi…"); quotes come from the golden file.
interface Meta {
  bucket: Finding['bucket']
  title: string
  detail: string
  visibleFrom: string
  resolvedOn?: string
}

const META: Record<string, Meta> = {
  C1: { bucket: 'conflict', title: 'Nesouhlasí data u apixabanu', detail: 'Nesoulad mezi datem výkonu (12. 10. 2026) a udaným vysazením apixabanu (poslední dávka 18. 10. 2026, znovu od 21. 10. 2026).', visibleFrom: '2026-10-12' },
  C2: { bucket: 'conflict', title: 'Nesouhlasí datum odběru vzorku', detail: 'Nesoulad mezi datem odběru uvedeným v histologii (20. 10. 2026) a datem vydání (19. 10. 2026).', visibleFrom: '2026-10-19' },
  C3: { bucket: 'document', title: 'Termín výsledku histologie', detail: 'V dokumentaci uvedeno: výsledek do 3 pracovních dnů. Eskalace 16. 10. 2026.', visibleFrom: '2026-10-16' },
  M1: { bucket: 'missing', title: 'Chybí stav výkonnosti (ECOG/Karnofsky)', detail: 'V dokumentaci je uvedeno pouze „Soběstačná“. Hodnota se nedovozuje.', visibleFrom: '2026-10-02' },
  M2: { bucket: 'missing', title: 'Chybí klinické TNM', detail: 'Klinické stadium není v dokumentaci uvedeno.', visibleFrom: '2026-10-02' },
  M3: { bucket: 'missing', title: 'Chybí e-mail pacientky a odesílajícího lékaře', detail: 'Kontaktní e-mail není v dokumentaci uveden.', visibleFrom: '2026-10-02' },
  S1: { bucket: 'stale', title: 'Zastaralá hmotnost', detail: 'Poslední uvedená hmotnost 65 kg z 15. 9. 2026; výška z 20. 7. 2026.', visibleFrom: '2026-10-08' },
  D1: { bucket: 'document', title: 'Chybí zpráva z kontroly u PL', detail: 'V dokumentaci zmíněna kontrola u PL 9. 9. 2026 s kontrolním odběrem; zpráva není přiložena.', visibleFrom: '2026-10-08' },
  D2: { bucket: 'missing', title: 'Výsledky 01–06 nejsou přiloženy', detail: 'V žádosti uvedeno: výsledky k dispozici na jednotlivých pracovištích.', visibleFrom: '2026-10-02', resolvedOn: '2026-10-08' },
  T1: { bucket: 'info', title: 'Zprávy po termínu as-of', detail: 'Zprávy 12 a 13 vznikly po začátku MDT a nejsou součástí handoveru.', visibleFrom: '2026-10-26' },
  X1: { bucket: 'info', title: 'Indikující lékař na CT', detail: 'Na CT je jako indikující lékař uvedena MUDr. Ivana Křížová, gastroenterolog; v žádosti je odesílající PL.', visibleFrom: '2026-10-08' },
  X4: { bucket: 'info', title: 'Pojišťovna 211', detail: 'ZP 211 je Zdravotní pojišťovna ministerstva vnitra ČR, nikoli VZP (111).', visibleFrom: '2026-10-02' },
  Q1: { bucket: 'info', title: 'Otázka pro MDT vyžaduje upřesnění', detail: 'Formulace otázky v žádosti je obecná.', visibleFrom: '2026-10-02' },
  N1: { bucket: 'info', title: 'Biliární drenáž není v dokumentaci uvedena', detail: 'V dokumentaci nenalezeno.', visibleFrom: '2026-10-19' },
}

export const FINDINGS: Finding[] = golden.expected_findings.flatMap((f) => {
  const m = META[f.id]
  if (!m) return []
  return [{ id: f.id, kind: f.kind, severity: f.severity, bucket: m.bucket, title: m.title, detail: m.detail, quotes: f.quotes ?? [], docIds: f.docs ?? [], visibleFrom: m.visibleFrom, resolvedOn: m.resolvedOn }]
})

/** Findings that exist on `today` (ISO date) and are not yet resolved. */
export function activeFindings(today: string): Finding[] {
  return FINDINGS.filter((f) => f.visibleFrom <= today && !(f.resolvedOn && f.resolvedOn <= today))
}

export function countFindings(today: string): { missing: number; conflict: number; stale: number } {
  const a = activeFindings(today)
  return {
    missing: a.filter((f) => f.bucket === 'missing').length,
    conflict: a.filter((f) => f.bucket === 'conflict').length,
    stale: a.filter((f) => f.bucket === 'stale').length,
  }
}
