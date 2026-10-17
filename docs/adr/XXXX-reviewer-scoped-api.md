# ADR-XXXX: Scoped API for the insurer reviewer and one computation of T1-T3

- Date: 2026-10-17 · Status: accepted (design delegated by the repo owner, #104, #105) · Owner: P4

## Context
- `GET /api/cases` answered the insurer's reviewer (revizní lékař, role `reviewer`) with the display name, birth date
  and insurer of every case (#104). The reviewer screen read a provisional `/api/reviewer/cases` mock (#105).
- Nothing computed the time-to-treatment proxies T1-T3; the case header always showed "zatím neběží".
- Definitions (docs/challenge-brief.md, golden `intervals_days`): T1 = first GP visit -> KOC referral, T2 = KOC
  referral -> MDT, T3 = MDT -> oncology consult. Proxies, labelled so. Demo case: 31 / 19 / 14 days.

## Decision
- **Intervals, once:** `backend/app/timeline/intervals.py`. Pure function over four optional anchors; days = whole
  calendar days between the Europe/Prague dates (10-02 09:30 -> 10-21 08:00 = 19, not 18). Each interval carries
  `days` (null unless both anchors are known) and `status`: `measured | running | not_started | not_recorded |
  inconsistent`. Nothing is estimated.
- **Anchors stored today:** KOC referral = `Case.opened_at`; MDT = `Case.mdt_start`, counted only once the MDT was
  held (state `zaver_mdt` or later; before that it is a plan). First GP visit (#188) and oncology consult (#189) are
  not stored, so live T1 is `not_recorded` and T3 stays `running` after the MDT. The golden 31/19/14 is asserted
  against the pure function with the golden anchors.
- **`CaseDetail.intervals`** (additive, always present) feeds the case header.
- **`GET /api/reviewer/cases` and `GET /api/reviewer/cases/{ref}`:** role `reviewer` only (others 403, checked before
  any read). Only cases whose patient is insured by the reviewer's insurer (the insurer Organization of the reviewer's
  PractitionerRole in the directory); a case of another insurer, or with no insurer, is 404 on the detail, so its
  existence is not confirmed. Fields: `ref` (pseudonym), `initials`, `birth_year`, `insurer_code`,
  `diagnosis_group` (MKN-10 category such as `C25`, no text), `state`, `referred_on`, `intervals`, `delivery`
  (`not_sent | handed_over | opened_by_gp | unconfirmed` + `gp_opened_at`). Never the name, birth date, birth number,
  contacts, documents or clinical text.
- **Pseudonym:** the case business id contains the surname, so the reviewer gets `RV-` + 12 hex of
  HMAC-SHA256(`JWT_SECRET`, `stafeta/reviewer-case-ref/v1:` + case id). Stable while the secret is; the label
  separates this use from token signing.
- **`GET /api/cases` and `GET /api/cases/{id}`** answer 403 to the reviewer (not a minimised variant: one shape per
  endpoint, and the reviewer has its own). Filtering for other roles stays with #16 / #35; the handover routes are #35.
- **Audit:** reads go through `CaseReader` as the acting reviewer: the list is one `search-type` AuditEvent, the
  detail adds a `read` of that one case. The list reads every case before the insurer filter (#190).

## Consequences
- Contract additive: new paths, new schemas `ReviewerCase`, `ReviewerDelivery`, `TimeToTreatmentIntervals`,
  `TreatmentInterval`; 401/403 documented on the case routes.
- The UI shows T1 as "nezaznamenáno" and T3 as "běží" in live mode until #188/#189 add the anchors; mocks follow the
  same semantics.
- Rotating `JWT_SECRET` changes every reviewer ref (bookmarks break; nothing is stored under the ref).
