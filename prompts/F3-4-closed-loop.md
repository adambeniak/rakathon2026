<!-- WHO: P4 (backend) + P3 (GP portal UI) · TOOL: Claude Code Sonnet 5.5 · MODE: normal · WHEN: F3 (04:00–08:00) -->

ROLE: Engineer closing the information loop with proof.

CONTEXT: MDT conclusion exists (F3-3). Mailpit runs in docker (SMTP 1025, UI 8025). Read demo-flow step 6,
AGENTS.md (audit, minimisation).

GOAL: The GP receives a clear, structured result with the original context; delivery and reading are proven; the
insurer's reviewer is informed automatically with a minimal summary; the case closes with a complete audit trail.

BUILD
1. `POST /api/cases/{id}/feedback/send` (coordinator, after human confirmation dialog) creates:
   - `Communication` to the GP: payload = MDT conclusion + recommendations + link to the full record PDF + "původní
     kontext" (referral letter reference, key handover sections). Status `in-progress`.
   - e-mail via SMTP to Mailpit with a secure link `/gp/inbox/{token}` (no clinical content in the e-mail body itself —
     only "Nová zpráva z KOC k Vašemu pacientovi").
   - reviewer summary for insurer 211: diagnosis code, MDT date, recommended treatment type, planned next date — no free
     text, no psychology/pain details (data minimisation). `Communication` to the reviewer role.
2. Delivery proof: SMTP accepted → `AuditEvent` (subtype transmit) + Communication.sent; GP opens the link → AuditEvent
   (read) + Communication.received + status `completed`; GP clicks "Potvrdit přijetí" → Task completed and case
   transition `zpetna_vazba_odeslana → uzavreno` when all closing tasks are done.
3. GP portal (P3): list of referred patients with state in plain Czech ("Přijato KOC 2 · čeká se na histologii ·
   MDT 21. 10."), what is missing from the GP (e.g. e-mail), the MDT result page, "Potvrdit přijetí".
4. Reviewer view (P3): read-only minimal summary + "Vyžádat doplnění" (creates a CommunicationRequest to the coordinator).
5. Audit tab: chronological AuditEvents with who/what/when, filter by type; export CSV.

ACCEPTANCE
- [ ] Mailpit shows the e-mail; opening the GP link creates the read receipt visible in the Audit tab
- [ ] Case reaches Uzavřeno only after the GP confirmation
- [ ] `security-privacy-reviewer` finds no PHI in e-mail bodies or logs; PRs `wf/closed-loop`, `fe/gp-reviewer`
