# ADR-XXXX: Insurer analytics over a fictitious cohort (`GET /api/insurer/analytics`)

- Date: 2026-10-17 · Status: accepted (product owner, F4 sprint; P1 to confirm the contract) · Owner: P2

## Context
- The VZP challenge asks for the insurer's view: durations of care and examinations, the delay between ordering and
  performing an examination per hospital, coordinator utilisation, the fastest and most cost-efficient hospitals, a
  quality indicator, per-coordinator and per-hospital stats incl. time per patient, and per case the dates of GP
  contact, CT, biopsy, MDT and treatment start with the intervals between them.
- The repository holds ONE real (fictitious) case, `rakathon-2026-prochazkova` at KOC 2, and one coordinator. There is
  no cost data and no order/perform timestamps for examinations as structured data. Ranking one case is meaningless.
- P1 is building the time-to-treatment proxies (`app/timeline/intervals.py`, branch `feat/reviewer-scoped-api`) and
  a scoped `/api/reviewer/...` API for the same reviewer role; neither is on `main` yet.

## Decision
- **Fixture, clearly simulated.** `backend/app/seed/data/insurer_cohort.json` (`tag: stafeta-demo`, `simulated: true`)
  holds 23 simulated journeys over four hospitals (KOC 1, KOC 2 and two invented "(simulace)" hospitals), seven
  coordinators (invented names marked "(simulace)" plus the seeded demo coordinator) and the demo case built from the
  golden dates: GP contact 2 Oct, CT done 8 Oct, biopsy done 12 Oct, MDT 21 Oct. No document states when CT and
  biopsy were ordered: both order dates are set to the GP request date (2 Oct) as a labelled demo assumption, stated in
  the API disclaimer shown on the screen.
  Its acceptance date, coordinator minutes and treatment start are **null** (not recorded; the 4 Nov oncology consult
  is planned, not a treatment start). Case codes are pseudonymous (`SIM-2026-014`); no names, RČ or birth dates.
- **Illustrative price list** in the same file (CZK, labelled "Ilustrativní ceník pro demo"), cost per case = sum of the
  recorded steps' prices.
- **Pure computation** in `app/timeline/insurer_analytics.py` (frozen dataclasses, mypy strict). Intervals are whole
  Europe/Prague calendar days between the anchors' Prague dates (the convention of `intervals.py`; same status values
  `measured | running | not_started | not_recorded | inconsistent`). A missing anchor gives `days = null`; an end before
  its start is `inconsistent`; nothing is estimated. Medians skip nulls.
- **Utilisation** = recorded coordinator minutes / (coordinators × assumed capacity per week × weeks of the cohort
  period). The capacity (120 min/week for these cases) is an explicit assumption returned in the response.
- **Operational indicator 0–100** (the brief's "quality indicator"; named operational because it does not measure quality of care) = 100 × (0.5 × speed + 0.3 × cost + 0.2 × target share), where speed and cost are inverted
  min-max scores of the hospital medians of "GP contact → MDT" and "cost per case" across the cohort (min == max → 1 for
  all, no division by zero) and target share = journeys with CT order → CT ≤ 7 days AND biopsy order → biopsy ≤ 10
  days (a demo assumption, labelled "Předpoklad pro demo"). Weights, targets, capacity, the formula text and the price
  list are returned so the UI shows the formula; the UI never recomputes a number. Ties share a rank (1, 1, 3) and are
  listed by name. Badges: `fastest` (lowest median contact → MDT), `lowest_cost`.
- **One additive endpoint** `GET /api/insurer/analytics` (`InsurerAnalytics`), role `reviewer` only: other roles get
  403 problem+json, no actor 401 (via `security.current_actor`). Wording is operational ("nejrychlejší v kohortě"),
  never a claim about quality of care; the response carries a Czech disclaimer the UI shows as a notice band.
- **No AuditEvent.** The endpoint reads no FHIR resource and no clinical content of a patient; it serves a static,
  pseudonymous, aggregated fixture. Rule 6 of AGENTS.md (audit every clinical read) is therefore not triggered.

## Consequences
- The insurer story is demonstrable today without touching FHIR, the case state machine or P1's files.
- The numbers are fictitious by construction; the screen and the API say so. Nobody may present them as real results.
- The demo case appears with honest gaps ("nezaznamenáno") instead of invented dates.
- Follow-ups: live data from FHIR (`ServiceRequest` authoredOn → `DiagnosticReport`/`Procedure` dates for order →
  exam, `Task` history and `AuditEvent` for coordinator time and acceptance, `EpisodeOfCare` for the hospital), then an
  AuditEvent per read; reuse `app.timeline.intervals.interval()` once it is on main (#191); a real price list
  (VZP sazebník / DRG) instead of the illustrative one; a validated indicator agreed with the insurer instead of
  the demo weights.
