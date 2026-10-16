export const inbox = {
  title: 'Fronta případů',
  columns: { new: 'Nový', active: 'Aktivní', snoozed: 'Odložený' },
  claim: 'Převzít',
  claimAria: (name: string) => `Převzít případ: ${name}`,
  open: 'Otevřít případ',
  emptyColumn: 'Žádné případy',
  emptyColumnHint: 'Nové žádosti od praktických lékařů se zobrazí zde.',
  urgent: 'Urgentní',
  referredAt: 'Žádost',
  gp: 'PL',
  columnCount: (n: number) => `${n}`,
} as const
