// Strings of the documents feature (upload; the document list texts are in cases.ts).
export const documents = {
  uploadTitle: 'Přidat zprávu k případu',
  uploadHint: 'Vyberte zprávu ve formátu PDF nebo DOCX s textovou vrstvou (max. 10 MB). Název souboru se zachová.',
  uploadLabel: 'Soubor zprávy',
  uploadButton: 'Nahrát',
  uploading: 'Nahrávám…',
  uploaded: (name: string) => `Nahráno: ${name}`,
  uploadFailed: (name: string, title: string) => `Nepodařilo se nahrát ${name}: ${title}`,
  coordinatorOnly: 'Zprávy k případu přidává koordinátorka KOC.',
} as const
