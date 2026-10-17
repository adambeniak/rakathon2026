"""Consistency detector: conflicting dates, SLA breaches, missing/stale data across documents (owner: P2).

Produces `app.domain.finding.Finding` items with neutral wording ("nesoulad mezi…", "chybí…") and evidence.
`detect_findings(facts)` runs the deterministic date-conflict rules C1/C2 over already as-of-filtered facts.
"""

from app.consistency.date_conflicts import detect_findings

__all__ = ["detect_findings"]
