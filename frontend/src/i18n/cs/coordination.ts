// Strings of the coordination feature (pathway launch, task board, task transitions).
export const coordination = {
  title: 'Úkoly',
  board: 'Kdo je na tahu',
  empty: 'Žádné úkoly',
  emptyHint: 'Úkoly vznikají spuštěním sady „Karcinom pankreatu – diagnostika“.',
  asOf: (date: string) => `Stav k ${date}`,
  laneEmpty: 'Žádné úkoly',
  // Keys are the backend Role enum.
  lanes: {
    gp: 'PL',
    coordinator: 'Koordinátor',
    koc_physician: 'Lékař KOC',
    koc_staff: 'Pracovník KOC',
    external_workplace: 'Externí pracoviště',
    patient: 'Pacient',
    reviewer: 'Revizní lékař',
    system: 'Systém',
  },
  launch: {
    open: 'Spustit sadu: Karcinom pankreatu – diagnostika',
    title: 'Spustit sadu: Karcinom pankreatu – diagnostika',
    hint: 'Sadu indikuje lékař KOC; koordinátorka ji spouští v jeho zastoupení.',
    startDate: 'Začátek sady',
    indicatedBy: 'Indikující lékař KOC',
    mdtStart: 'Plánovaný začátek MDT',
    submit: 'Spustit sadu',
    submitting: 'Spouštím…',
    cancel: 'Zrušit',
    error: 'Sadu se nepodařilo spustit.',
  },
  task: {
    owner: 'Vlastník',
    /** A step without a named person (external workplaces; KOC steps before anyone took them). */
    ownerUnassigned: 'nepřiřazeno',
    place: 'Místo',
    due: 'Termín',
    scheduled: 'Potvrzený termín',
    sla: 'Slíbeno do',
    placeUnknown: 'zatím nepotvrzeno',
    blockedBy: (title: string) => `Čeká na: ${title}`,
    overdue: (workdays: number) =>
      workdays > 0
        ? `Po termínu ${workdays} ${workdays === 1 ? 'pracovní den' : workdays < 5 ? 'pracovní dny' : 'pracovních dní'}`
        : 'Po termínu',
    escalated: (date: string) => `Eskalováno ${date}`,
    onBehalf: (name: string) => `Zaznamenal(a) za pracoviště: ${name}`,
    result: (docId: string) => `Výsledek: ${docId}`,
    businessStatus: {
      objednano: 'K objednání',
      potvrzeno: 'Objednáno',
      provedeno: 'Provedeno',
      vysledek_dorucen: 'Výsledek doručen',
    },
    status: { failed: 'Selhalo', cancelled: 'Zrušeno' },
  },
  actions: {
    confirm: 'Potvrdit objednání',
    perform: 'Provedeno',
    deliver: 'Výsledek doručen',
    aria: (action: string, title: string) => `${action}: ${title}`,
  },
  confirmForm: {
    hint: 'Odeslaná žádanka není objednané vyšetření: zadejte pracoviště a skutečný termín.',
    place: 'Pracoviště',
    date: 'Datum vyšetření',
    submit: 'Potvrdit',
    cancel: 'Zrušit',
  },
  deliverForm: {
    hint: 'Vyberte dokument s výsledkem, který je k případu přiložen.',
    document: 'Dokument s výsledkem',
    choose: 'Vyberte dokument',
    noDocuments: 'K případu zatím není přiložen žádný dokument.',
    submit: 'Potvrdit doručení',
    cancel: 'Zrušit',
  },
  baton: {
    action: (title: string) => title,
    awaiting_confirmation: (title: string) => `Potvrdit objednání: ${title}`,
    dependency_failed: (title: string) => `Předchozí krok selhal nebo byl zrušen: ${title}`,
  },
  transitionError: 'Změnu se nepodařilo uložit.',
  clock: {
    error: 'Demo hodiny na serveru se nepodařilo nastavit.',
  },
} as const
