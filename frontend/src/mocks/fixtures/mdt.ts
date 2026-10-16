// MOCK copy – replaced by API in F2/F3
import type { DocumentInfo, HandoverSection } from '@/lib/domain'
import { DOCUMENTS, includedAt } from './documents'
import { activeFindings } from './findings'
import { CONFIRMABLE } from './handover'

export interface GateItem {
  id: string
  level: 'ok' | 'blocker' | 'warning' | 'info'
  label: string
  detail?: string
}

export interface MdtView {
  asOf: string
  gate: GateItem[]
  ready: boolean
  included: DocumentInfo[]
  excluded: Array<DocumentInfo & { reason: string }>
  generatedAt: string | null
}

export function buildMdt(asOf: string, sections: HandoverSection[], generatedAt: string | null): MdtView {
  const day = asOf.slice(0, 10)
  const included = includedAt(asOf)
  const excluded = DOCUMENTS.filter((d) => !included.includes(d)).map((d) => ({
    ...d,
    reason: 'po MDT – vznik nebo přijetí po termínu as-of',
  }))
  const confirmable = sections.filter(CONFIRMABLE)
  const done = confirmable.filter((s) => s.confirmed).length
  const findings = activeFindings(day)
  const missing = findings.filter((f) => f.bucket === 'missing')
  const conflict = findings.filter((f) => f.bucket === 'conflict')
  const stale = findings.filter((f) => f.bucket === 'stale')
  const hasHistology = included.some((d) => d.id.startsWith('11_'))
  const gate: GateItem[] = [
    hasHistology
      ? { id: 'histology', level: 'ok', label: 'Histologie je k as-of k dispozici' }
      : { id: 'histology', level: 'blocker', label: 'K termínu as-of chybí histologie', detail: 'Zpráva 11 vznikla po zvoleném termínu.' },
    done === confirmable.length
      ? { id: 'sections', level: 'ok', label: `Potvrzeno lékařem: ${done} z ${confirmable.length} sekcí` }
      : { id: 'sections', level: 'blocker', label: `Nepotvrzeno lékařem: ${confirmable.length - done} z ${confirmable.length} sekcí`, detail: 'Potvrďte sekce v handoveru.' },
    missing.length > 0
      ? { id: 'missing', level: 'warning', label: `Chybí údaje: ${missing.length}`, detail: missing.map((m) => m.title).join(' · ') }
      : { id: 'missing', level: 'ok', label: 'Žádné chybějící údaje' },
    conflict.length > 0
      ? { id: 'conflict', level: 'warning', label: `Nesoulady k ověření: ${conflict.length}`, detail: conflict.map((m) => m.title).join(' · ') }
      : { id: 'conflict', level: 'ok', label: 'Žádné nesoulady' },
    ...(stale.length > 0 ? [{ id: 'stale', level: 'warning' as const, label: `Zastaralé údaje: ${stale.length}`, detail: stale.map((m) => m.title).join(' · ') }] : []),
    ...(excluded.length > 0 ? [{ id: 'excluded', level: 'info' as const, label: `Mimo handover (po MDT): ${excluded.length} zprávy`, detail: excluded.map((d) => d.id.slice(0, 2)).join(', ') }] : []),
  ]
  return { asOf, gate, ready: !gate.some((g) => g.level === 'blocker'), included, excluded, generatedAt }
}
