// Aggregates every feature file in this folder: { common, inbox, handover, coordination, documents, ... }.
const modules = import.meta.glob<Record<string, unknown>>('./*.ts', { eager: true })

export const cs = Object.fromEntries(
  Object.entries(modules)
    .filter(([path]) => !path.endsWith('/index.ts'))
    .flatMap(([, m]) => Object.entries(m)),
) as Record<string, unknown>
