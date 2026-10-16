<!-- WHO: P3 · TOOL: Claude Code Sonnet 5.5 + frontend-design skill + ux-reviewer subagent · MODE: normal · WHEN: F4 (08:00–11:00) -->

ROLE: Product designer-engineer doing the final polish of a clinical app before a jury demo.

GOAL: In the 6 demo screens, a judge understands within 3 seconds: where the case is, who holds the baton and until when,
what is missing or conflicting, and that every AI value has a source.

DO
1. Run `ux-reviewer` on each demo step; fix the top issues per screen.
2. Consistency pass: spacing, type scale, status pills (icon + text), Czech wording and diacritics, dates `21. 10. 2026`,
   no English, no raw IDs on screen, empty/error/loading states with guidance.
3. "Wow" moments get visual emphasis (subtle, not flashy): evidence popover with highlighted quote; conflict card
   showing both sources side by side; as-of slider greying out reports 12–13; T1/T2/T3 clocks; delivery receipt.
4. Accessibility: contrast AA, focus visible, keyboard path through the demo, `aria-live` for toasts.
5. Projector check: 1280×720 and 1920×1080, browser zoom 125 %.

CONSTRAINTS: No new features after 11:30. No layout changes that break E2E selectors without updating `frontend/e2e`
(coordinate with P4).

ACCEPTANCE
- [ ] Before/after screenshots for each demo screen in PR `fe/polish`
- [ ] E2E still green
