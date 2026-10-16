import type { DocumentInfo, HandoverSection } from '@/lib/domain'

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
  sections: HandoverSection[]
}
