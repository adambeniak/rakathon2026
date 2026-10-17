export const gp = {
  title: 'Moji odeslaní pacienti',
  cols: { patient: 'Pacientka / pacient', state: 'Stav', missing: 'Co chybí', baton: 'Na tahu' },
  empty: 'Zatím jste neodeslal(a) žádnou žádost',
  emptyHint: 'Novou žádost o převzetí do KOC vytvoříte přetažením dokumentu.',
  newReferral: 'Nová žádost',
  nothingMissing: 'Nic nechybí',
  mdtTitle: 'Závěr MDT k otevření',
  // The relay accepted the notification e-mail; that is not a read or delivery receipt.
  mdtText:
    'Oznámení o závěru KOC/MDT bylo předáno k doručení do vaší ordinace. Závěr si můžete otevřít zde.',
  openConclusion: 'Otevřít závěr MDT',
  openConclusionAria: (name: string) => `Otevřít závěr MDT: ${name}`,
  closeConclusion: 'Skrýt závěr',
  conclusionLoading: 'Načítám závěr…',
  conclusionHeading: 'Závěr MDT',
  signedBy: (name: string, at: string) => `Podepsal(a) ${name} dne ${at}`,
  openedRecorded: 'Otevření závěru bylo zaznamenáno do auditní stopy.',
  openedFailed: 'Otevření závěru se nepodařilo zaznamenat.',
  openedRetry: 'Zkusit znovu',
  openCase: 'Otevřít',
} as const
