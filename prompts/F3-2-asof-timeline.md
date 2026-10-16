<!-- WHO: P1 (backend) + P3 (UI, separate session) · TOOL: Claude Code Sonnet 5.5 · MODE: normal · WHEN: F3 -->

ROLE: Full-stack engineer making time visible: what was known when, and where days were lost.

CONTEXT: Documents carry authored (attachment.creation) and received (DocumentReference.date) timestamps; tasks have
dates; the golden file has `timeline` and `intervals_days` (T1 31 d, T2 19 d, T3 14 d, total 64 d). These are
PROXIES (T1 from the first GP visit because symptom onset is approximate; T3 ends at the oncology consult) — label them
so in the UI tooltip. Read the
demo-flow skill and docs/challenge-brief.md (T1/T2/T3 definition).

BACKEND (P1)
1. `GET /api/cases/{id}/timeline?as_of=` → ordered events (symptom onset, first GP visit, suspicion, referral,
   each exam/result, MDT, planned consult) with source (document/task), authored vs received, and `known_at_as_of`.
2. `GET /api/cases/{id}/time-to-treatment` → T1 (first GP contact → KOC referral), T2 (referral → MDT),
   T3 (MDT → treatment/consult), suspicion → referral, plus "waiting segments" classified as organizační
   (e.g. waiting for a CT slot, histology over SLA) vs klinická příprava (e.g. apixaban pause) — classification comes
   from task types, not from AI. Benchmark constant: VZP example patient 21 days (label as illustrative).
3. As-of everywhere: one query parameter, one helper; add tests that reports 12–13 vanish at 21. 10. and appear at 28. 10.

UI (P3, separate prompt run)
4. Case header: three compact clocks T1 / T2 / T3 (days, colour only with text), tooltip with definition.
5. "Časová osa" tab: horizontal timeline (to scale) with lanes PL · KOC 1 · KOC 2 · Pacient; events as dots, waiting
   segments as bars; an as-of slider/date picker that greys out what was not known yet ("po MDT" badge for 12–13).
6. MDT screen uses the same as-of picker, defaulting to the MDT date.

ACCEPTANCE
- [ ] Numbers match the golden `intervals_days`
- [ ] Moving the as-of date changes timeline, handover and findings consistently (one source of truth)
- [ ] PRs `be/timeline` and `fe/timeline`
