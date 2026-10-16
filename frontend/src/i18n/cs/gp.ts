export const gp = {
  title: 'Moji odeslaní pacienti',
  cols: { patient: 'Pacientka / pacient', state: 'Stav', missing: 'Co chybí', baton: 'Na tahu' },
  empty: 'Zatím jste neodeslal(a) žádnou žádost',
  emptyHint: 'Novou žádost o převzetí do KOC vytvoříte přetažením dokumentu.',
  newReferral: 'Nová žádost',
  nothingMissing: 'Nic nechybí',
  mdtTitle: 'Závěr MDT k potvrzení',
  mdtText: 'Závěr KOC/MDT byl odeslán do vaší ordinace. Potvrďte prosím přijetí.',
  acknowledge: 'Potvrdit přijetí',
  acknowledgeAria: (name: string) => `Potvrdit přijetí závěru MDT: ${name}`,
  openCase: 'Otevřít',
} as const
