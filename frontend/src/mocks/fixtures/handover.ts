// MOCK copy – replaced by API in F2/F3
import type { HandoverSection, HandoverStatus } from '@/lib/domain'
import { formatDate } from '@/lib/date'
import { handover as t } from '@/i18n/cs/handover'
import { AS_OF_DEFAULT, includedAt } from './documents'
import type { RowEdit } from './cases'
import { golden } from './golden'

type Row = HandoverSection['rows'][number]
type Gf = (typeof golden.fields)[string]

const FINDING_LINKS: Record<string, string[]> = {
  '2_contacts': ['M3'],
  '3_diagnosis': ['M2'],
  '5_mdt_question': ['Q1'],
  '7_medications': ['C1'],
  '9_performance_status': ['M1'],
  '10_weight_height': ['S1'],
  '14_histology': ['C2'],
}

const S = (v: unknown): string => (v === null || v === undefined ? '' : String(v))
const obj = (v: unknown): Record<string, unknown> => (v ?? {}) as Record<string, unknown>
const arr = (v: unknown): Array<Record<string, unknown>> => (Array.isArray(v) ? (v as Array<Record<string, unknown>>) : [])

const SEX: Record<string, string> = { female: 'žena', male: 'muž' }

function rowsFor(key: string, f: Gf, inc: Set<string>): Row[] {
  const v = obj(f.value)
  switch (key) {
    case '1_patient':
      return [
        { label: 'Jméno', value: `${S(v.given)} ${S(v.family)}` },
        { label: 'Pohlaví', value: SEX[S(v.sex)] ?? S(v.sex) },
        { label: 'Narození', value: `${formatDate(S(v.birth_date))} (${S(v.age_years)} let)` },
        { label: 'Rodné číslo', value: S(v.birth_number), note: v.birth_number_checksum_valid ? 'kontrolní součet v pořádku' : undefined },
        { label: 'Pojišťovna', value: `${S(v.insurer_code)} – ${S(v.insurer_name)}` },
        { label: 'Adresa', value: S(v.address) },
      ]
    case '2_contacts': {
      const c = obj(v.contact_person)
      return [
        { label: 'Telefon pacientky', value: S(v.patient_phone) },
        { label: 'Kontaktní osoba', value: `${S(c.name)} (${S(c.relation)}), ${S(c.phone)}` },
      ]
    }
    case '3_diagnosis':
      return [
        { label: 'MKN-10', value: S(v.icd10) },
        { label: 'Popis', value: S(v.text) },
        { label: 'MKN-O morfologie', value: S(v.icdo3_morphology) },
        { label: 'Histologicky ověřeno', value: formatDate(S(v.verified_histologically_on)) },
      ]
    case '4_epicrisis':
      return [] // composed in buildSections from the documents available at the cutoff
    case '5_mdt_question':
      return [{ value: S(f.value) }]
    case '6_comorbidities':
      return arr(f.value).map((c) => ({ value: S(c.text), note: [c.icd10, c.detail].filter(Boolean).join(' · ') || undefined }))
    case '7_medications':
      return arr(f.value).map((m) => ({ label: S(m.drug), value: `${S(m.dose)}, ${S(m.schedule)}` }))
    case '8_allergies':
      return [{ value: S(f.value) }]
    case '9_performance_status':
      return [{ value: 'Neuvedeno', note: 'V dokumentaci je uvedeno pouze „Soběstačná“; ECOG/Karnofsky se nedovozuje.' }]
    case '10_weight_height': {
      return [
        { label: 'Výška', value: `${S(v.height_cm)} cm`, note: formatDate(S(v.height_date)) },
        ...arr(v.weights).map((w) => ({ label: 'Hmotnost', value: `${S(w.kg)} kg`, note: formatDate(S(w.date)) })),
      ]
    }
    case '11_symptoms':
      return [
        { label: 'Začátek', value: S(v.onset) },
        ...((v.items as string[] | undefined) ?? []).map((i) => ({ value: i })),
      ]
    case '12_examinations':
      return arr(f.value)
        .filter((e) => inc.has(S(e.doc)))
        .map((e) => ({ label: formatDate(S(e.date)), value: `${S(e.type)} – ${S(e.place)}` }))
    case '13_labs':
      return (f.key_values ?? []).filter((l) => inc.has(l.doc)).map((l) => ({
        label: `${l.test} (${formatDate(l.date)})`,
        value: `${String(l.value).replace('.', ',')} ${l.unit}${l.flag ? ` ${l.flag}` : ''}`,
      }))
    case '14_histology': {
      const ihc = obj(v.ihc)
      return [
        { label: 'Číslo nálezu', value: S(v.report_id) },
        { label: 'Vydáno', value: formatDate(S(v.issued)) },
        { label: 'Grade', value: S(v.grade) },
        { label: 'Perineurální invaze', value: v.perineural_invasion ? 'ano' : 'ne' },
        { label: 'IHC', value: Object.entries(ihc).map(([k, x]) => `${k} ${S(x)}`).join(', ') },
      ]
    }
    case '15_other':
      return ((f.value as string[] | undefined) ?? []).map((i) => {
        const ev = (f.evidence ?? []).find((e) => e.quote === i)
        // The API marks consent / wishes of the patient: read-only, with their own source.
        return /^Souhlas/.test(i) && ev ? { value: i, readOnly: true, evidence: [{ docId: ev.doc, quote: ev.quote }] } : { value: i }
      })
    default:
      return []
  }
}

const DOC = {
  uz: '06_UZ_bricha_2026-09-29',
  ct: '08_CT_KOC1_2026-10-08',
  eus: '09_Biopsie_vykon_KOC2_2026-10-12',
  labs: '10_Laborator_KOC2_2026-10-15',
  hist: '11_Histologie_KOC2_2026-10-19',
  referral: '07_PL_zadost_KOC2_2026-10-02',
  lab1: '02_Laborator_2026-09-01',
} as const

const quoteOf = (key: string, doc: string): string | undefined => golden.fields[key]?.evidence?.find((e) => e.doc === doc)?.quote
const findingQuote = (id: string, i: number): string | undefined => golden.expected_findings.find((x) => x.id === id)?.quotes?.[i]

/** AI epikríza draft: every statement is paired with evidence from a document available at the cutoff. */
function epicrisis(inc: Set<string>): Pick<HandoverSection, 'rows' | 'evidence'> {
  const parts: Array<{ text: string; ev: HandoverSection['evidence'][number] }> = [
    { text: 'od poloviny srpna 2026 bolesti v epigastriu a pravém podžebří', ev: { docId: DOC.referral, quote: quoteOf('11_symptoms', DOC.referral) } },
    { text: 'bilirubin celkový 38 µmol/l H (1. 9. 2026)', ev: { docId: DOC.lab1 } },
    { text: 'UZ břicha 29. 9. 2026', ev: { docId: DOC.uz } },
    { text: 'ložisko hlavy pankreatu suspektní z malignity', ev: { docId: DOC.referral, quote: quoteOf('4_epicrisis', DOC.referral) } },
    { text: 'CT 8. 10. 2026 – tumor hlavy pankreatu 35 mm', ev: { docId: DOC.ct, quote: quoteOf('4_epicrisis', DOC.ct) } },
    { text: 'EUS-FNB 12. 10. 2026', ev: { docId: DOC.eus, quote: findingQuote('C1', 0) } },
    { text: 'CA 19-9 312 kU/l H (15. 10. 2026)', ev: { docId: DOC.labs } },
    { text: 'histologie vydána 19. 10. 2026 – duktální adenokarcinom pankreatu', ev: { docId: DOC.hist, quote: quoteOf('3_diagnosis', DOC.hist) } },
  ]
  const used = parts.filter((p) => inc.has(p.ev.docId))
  return {
    rows: [{ value: `V dokumentaci uvedeno: ${used.map((p) => p.text).join('; ')}.` }],
    evidence: used.map((p) => p.ev),
  }
}

export function buildSections(confirmed: Record<string, string>, asOf: string = AS_OF_DEFAULT): HandoverSection[] {
  const inc = new Set(includedAt(asOf).map((d) => d.id))
  const hasHistology = inc.has(DOC.hist)
  return Object.entries(golden.fields).map(([key, f]) => {
    const number = Number(key.split('_')[0])
    const evidenceAll: HandoverSection['evidence'] = [
      ...(f.evidence ?? []).map((e) => ({ docId: e.doc, quote: e.quote })),
      ...(f.key_values ? [...new Set(f.key_values.map((k) => k.doc))].map((docId) => ({ docId })) : []),
      ...(key === '12_examinations' ? [...new Set(arr(f.value).map((e) => S(e.doc)))].map((docId) => ({ docId })) : []),
    ]
    let rows = rowsFor(key, f, inc)
    let evidence = evidenceAll.filter((e) => inc.has(e.docId))
    let status = f.status as HandoverStatus
    let findingIds = FINDING_LINKS[key] ?? []

    if (key === '4_epicrisis') ({ rows, evidence } = epicrisis(inc))
    if (key === '3_diagnosis' && !hasHistology) {
      // Before the histology report only the suspected diagnosis from the referral may be shown.
      rows = [
        { label: 'MKN-10', value: S(obj(f.value).icd10) },
        { label: 'Popis', value: 'suspektní tumor hlavy pankreatu' },
      ]
      evidence = [{ docId: DOC.referral, quote: 'C25.0 – suspektní tumor hlavy pankreatu' }]
    }
    if (key === '14_histology' && !hasHistology) {
      rows = [{ value: 'Neuvedeno' }]
      status = 'missing'
      findingIds = []
    }
    // A section whose every source lies beyond the cutoff has no supported value.
    if (evidenceAll.length > 0 && evidence.length === 0 && key !== '14_histology') {
      rows = [{ value: 'Neuvedeno' }]
      status = 'missing'
      findingIds = []
    }

    return {
      key,
      number,
      title: (t.sectionTitles as Record<string, string>)[key] ?? key,
      status,
      rows,
      missing: (f.missing ?? []).map((m) => (t.missingItems as Record<string, string>)[m] ?? m),
      evidence,
      findingIds,
      confirmed: key in confirmed,
      confirmedBy: confirmed[key],
    }
  })
}

/** Stand-in for the API's SHA-256 `value_hash`: changes whenever the displayed values change. */
export function sectionHash(s: HandoverSection): string {
  let h = 5381
  for (const ch of JSON.stringify(s.rows.map((r) => [r.label, r.value]))) h = (h * 33) ^ ch.charCodeAt(0)
  return (h >>> 0).toString(16).padStart(8, '0').repeat(8)
}

export const CONFIRMABLE = (s: HandoverSection): boolean => s.status !== 'missing'

/** Overlays the clinician's corrections on the assembled sections; each row shows the note of its own edit. */
export function applyEdits(sections: HandoverSection[], edits: Record<string, Record<number, RowEdit>>): HandoverSection[] {
  return sections.map((s) => {
    const rowEdits = edits[s.key]
    if (!rowEdits) return s
    return {
      ...s,
      rows: s.rows.map((r, i) => {
        const e = rowEdits[i]
        return e ? { ...r, value: e.value, note: t.editedNote(e.by, e.at, e.reason) } : r
      }),
    }
  })
}

/** The one builder for handover and MDT: assembled sections with confirmations and edits applied. */
export function buildReviewedSections(
  confirmed: Record<string, string>,
  edits: Record<string, Record<number, RowEdit>>,
  asOf: string = AS_OF_DEFAULT,
): HandoverSection[] {
  return applyEdits(buildSections(confirmed, asOf), edits)
}
