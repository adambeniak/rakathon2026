---
applyTo: "frontend/**/*.ts,frontend/**/*.tsx,frontend/**/*.css"
---
Follow `.claude/rules/frontend.md` (full frontend rules). Critical points:
- Generated API client + TanStack Query only; never hand-write API types.
- UI text in `src/i18n/cs/<feature>.ts` (Czech), one file per feature. Dates `d. M. yyyy` with `cs` locale.
- Status colours fixed (Chybí red, Nesouhlasí amber, Zastaralé grey, Ověřeno green, Návrh AI violet) + icon + text.
- AI values always rendered with `<EvidenceChip>`.
- Accessible markup; Playwright tests select by role and Czech label.
