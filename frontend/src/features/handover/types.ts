import type { DocumentInfo, HandoverSection } from '@/lib/domain'

export interface HandoverView {
  asOf: string
  sections: HandoverSection[]
  excluded: DocumentInfo[]
}
