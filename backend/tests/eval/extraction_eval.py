"""Extraction eval vs the golden set (used by `make eval` via test_extraction_eval.py).

Writes eval/report.json (repo root); the very first run is also kept as eval/report_first_run.json.
Hard gates: evidence validity 100 %, hallucinations 0, as-of leakage 0. Documents carry the seed's
received_at, and the as-of filter runs with require_received=True (backend path).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.documents.normalize import NormalizedDoc, match_key, normalize, normalize_text
from app.domain.document import SourceDocument
from app.domain.evidence import Fact
from app.extraction.lock import (
    NEGATED_VALUE_REPAIRED,
    PS_CUE,
    fact_quote,
    filter_as_of,
    stated_with_negation_cue,
)
from app.extraction.pipeline import CompletionClient, DocExtraction, extract_facts
from app.extraction.prompt import PROMPT_VERSION
from app.extraction.values import DateValue, QuantityValue, parse_value
from app.seed.demo_case import DOCUMENTS, MDT_START
from app.settings import REPO_ROOT
from tests.eval.golden_atoms import build_atoms, coverage_items, text_coverage
from tests.eval.injection import injection_smoke

REPO = REPO_ROOT
GOLDEN = REPO / "data" / "golden" / "expected_handover_2026-10-21.json"
DOCS_DIR = REPO / "data" / "raw" / "Pacient"
AS_OF = MDT_START  # 2026-10-21T08:00:00+02:00
RECALL_TARGET = 0.90
REPORT = REPO / "eval" / "report.json"


def source_documents() -> dict[str, SourceDocument]:
    """P1's seed metadata: authored + received timestamps for the as-of rule (demo assumptions)."""
    return {
        d.doc_id: SourceDocument(
            doc_id=d.doc_id,
            title=d.title,
            type_code=d.loinc,
            authored_at=d.authored_at,
            received_at=d.received_at,
            file_name=d.file_name,
        )
        for d in DOCUMENTS
    }


def load_docs() -> dict[str, NormalizedDoc]:
    sources = source_documents()
    return {p.stem: normalize(p, sources.get(p.stem)) for p in sorted(DOCS_DIR.glob("*.docx"))}


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 - fixed argv, report metadata only
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# ---------------------------------------------------------------- independent audits (do not reuse the lock code)


def _independent_quote_ok(fact: Fact, fresh: NormalizedDoc) -> bool:
    ev = fact.evidence[0]
    if ev.char_start is None or ev.char_end is None or fresh.text[ev.char_start : ev.char_end] != ev.quote:
        return False
    return " ".join(ev.quote.split()) in " ".join(fresh.text.split())


def _value_tokens_ok(fact: Fact) -> list[str]:
    """Every digit run in the value must occur in the quote (NFKC, comma/point agnostic)."""
    quote = unicodedata.normalize("NFKC", fact_quote(fact)).replace(",", ".")
    problems: list[str] = []
    v = parse_value(fact.value)
    texts: list[str] = []
    for k, item in v.model_dump().items():
        if k in {"kind", "system", "flag", "comparator", "number"} or isinstance(v, DateValue):
            continue
        if isinstance(item, str):
            texts.append(item)
    if isinstance(v, QuantityValue) and v.number is not None:
        n = v.number
        texts.append(str(int(n)) if float(n).is_integer() else repr(n))
    # Compare numerically: the source writes "4,20", the model returns 4.2 (run 1 flagged these as
    # false positives when this audit compared strings).
    quote_values = {float(q) for q in re.findall(r"\d+(?:\.\d+)?", quote)}
    for t in texts:
        t = re.sub(r"\b\d{4}-\d{2}(-\d{2})?\b", " ", unicodedata.normalize("NFKC", t)).replace(",", ".")
        for tok in re.findall(r"\d+(?:\.\d+)?", t):
            if not any(abs(float(tok) - q) < 1e-9 for q in quote_values):
                problems.append(tok)
    return problems


# ---------------------------------------------------------------- main


async def run(client: CompletionClient, model: str, as_of: datetime = AS_OF) -> dict[str, Any]:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    paths = sorted(DOCS_DIR.glob("*.docx"))
    docs = load_docs()
    # sequential gather is fine: the client limits concurrency itself
    results: list[DocExtraction] = [await extract_facts(d, client) for d in docs.values()]
    injection = await injection_smoke(client)

    raw_total = sum(len(r.raw) for r in results)
    raw_exact = 0
    for r in results:
        key = match_key(docs[r.doc_id].text).key
        raw_exact += sum(1 for f in r.raw if match_key(normalize_text(f.quote)).key in key)
    accepted_all = [f for r in results for f in r.accepted]
    final = filter_as_of(accepted_all, docs, as_of, require_received=True)
    excluded = {e["doc"] for e in golden["excluded_documents"]}
    included_run = {f.doc_id for f in final}

    # evidence validity: re-normalise from DOCX independently
    fresh = {p.stem: normalize(p) for p in paths}  # without seed metadata: text only
    invalid = [f for f in final if not _independent_quote_ok(f, fresh[f.doc_id])]

    # hallucination audit
    halluc: list[dict[str, Any]] = []
    for f in final:
        probs = _value_tokens_ok(f)
        if probs:
            halluc.append({"fact_id": f.id, "doc": f.doc_id, "why": f"value numbers not in quote: {probs}"})
        if f.type == "performance_status" and not PS_CUE.search(fact_quote(f)):
            halluc.append({"fact_id": f.id, "doc": f.doc_id, "why": "PS without ECOG/Karnofsky"})
    atoms = build_atoms(golden)
    negative_hits = [a for a in atoms if a.negative and a.match(final)]
    for a in negative_hits:
        halluc.append({"atom": a.atom_id, "why": f"negative atom hit: {a.description}"})

    leakage = [f for f in final if f.doc_id in excluded]
    excluded_extracted = sum(1 for f in accepted_all if f.doc_id in excluded)

    positive = [a for a in atoms if not a.negative]
    hits = [a for a in positive if a.match(final)]
    misses = [a for a in positive if a not in hits]
    recall = len(hits) / len(positive) if positive else 0.0

    cov: list[dict[str, Any]] = []
    for field, text, types in coverage_items(golden):
        cands = [f for f in final if f.type in types]
        cov.append({"field": field, "text": text, "coverage": round(text_coverage(text, cands), 2)})

    reasons = Counter(rj.reason for r in results for rj in r.rejected)
    per_doc = [
        {
            "doc": r.doc_id,
            "raw": len(r.raw),
            "accepted": len(r.accepted),
            "rejected": len(r.rejected),
            "in_handover": r.doc_id in {f.doc_id for f in final},
        }
        for r in results
    ]
    rejected_log = [
        {
            "doc": r.doc_id,
            "reason": rj.reason,
            "detail": rj.detail,
            "type": rj.raw.type if rj.raw else None,
            "quote": rj.raw.quote[:120] if rj.raw else None,
        }
        for r in results
        for rj in r.rejected
    ]

    gates = {
        "evidence_validity_100": bool(final) and not invalid,  # an empty run must not pass vacuously
        "hallucinations_0": not halluc,
        "as_of_leakage_0": not leakage,
    }
    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": _git_commit(),
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "as_of": as_of.isoformat(),
        "documents": len(docs),
        "included_documents": sorted(included_run - excluded),
        "metrics": {
            "raw_facts": raw_total,
            "raw_quote_validity": round(raw_exact / raw_total, 4) if raw_total else None,
            "accepted_facts": len(accepted_all),
            "repaired_quotes": sum(1 for f in accepted_all if f.quote_repaired),
            "negated_values_repaired": sum(1 for f in accepted_all if NEGATED_VALUE_REPAIRED in f.lock_notes),
            "clinical_dates_dropped": sum(1 for f in final if f.lock_notes),
            "facts_in_handover": len(final),
            "evidence_validity": round(1 - len(invalid) / len(final), 4) if final else None,
            "hallucinations": len(halluc),
            "as_of_leakage": len(leakage),
            "excluded_doc_facts_filtered": excluded_extracted,
            "docs_received_unknown": sum(1 for d in docs.values() if d.received_at is None),
            "key_value_recall": round(recall, 4),
            "key_values": f"{len(hits)}/{len(positive)}",
            "text_coverage_mean": round(sum(c["coverage"] for c in cov) / len(cov), 3) if cov else None,
            "stated_with_negation_cue": sum(1 for f in final if stated_with_negation_cue(f)),
            "field_status_accuracy": "n/a (handover assembly is F2-2)",
        },
        "gates": gates,
        "injection_smoke": injection,
        "recall_target": RECALL_TARGET,
        "misses": [{"atom": a.atom_id, "field": a.field, "expected": a.description} for a in misses],
        "excluded_from_recall": [
            "1.sex",
            "1.age_years",
            "1.insurer_name",
            "1.checksum",
            "4_epicrisis",
            "5_mdt_question",
        ],
        "hallucination_details": halluc,
        "rejections_by_reason": dict(reasons.most_common()),
        "rejected": rejected_log,
        "text_coverage": cov,
        "stated_with_negation_cue_facts": [
            {"doc": f.doc_id, "type": f.type, "quote": fact_quote(f)[:120]}
            for f in final
            if stated_with_negation_cue(f)
        ],
        "per_document": per_doc,
        "facts": [f.model_dump(mode="json") for f in final],
    }


def format_table(rep: dict[str, Any]) -> str:
    m = rep["metrics"]
    rows = [
        ("Raw quote validity (model)", m["raw_quote_validity"], ""),
        ("Evidence validity", m["evidence_validity"], "gate 100 %"),
        ("Hallucinations", m["hallucinations"], "gate 0"),
        ("As-of leakage", m["as_of_leakage"], f"gate 0 ({m['excluded_doc_facts_filtered']} facts filtered)"),
        ("Key value recall", f"{m['key_value_recall']:.1%} ({m['key_values']})", f"target ≥ {RECALL_TARGET:.0%}"),
        ("Text coverage (mean)", m["text_coverage_mean"], "info"),
        ("Facts raw / accepted / handover", f"{m['raw_facts']} / {m['accepted_facts']} / {m['facts_in_handover']}", ""),
        ("Repaired quotes", m["repaired_quotes"], ""),
        ("Negated values from quote", m["negated_values_repaired"], "lock repair, audit"),
        ("Stated with negation cue", m["stated_with_negation_cue"], "audit"),
    ]
    lines = [f"Štafeta extraction eval · {rep['model']} · {rep['prompt_version']} · commit {rep['commit']}"]
    lines += [f"  {name:<34} {val!s:<22} {note}" for name, val, note in rows]
    lines.append(f"  Rejections: {rep['rejections_by_reason'] or 'none'}")
    if rep["misses"]:
        lines.append("  Misses:")
        lines += [f"    - {miss['atom']}: {miss['expected']}" for miss in rep["misses"]]
    lines += [f"  HALLUCINATION: {h}" for h in rep["hallucination_details"]]
    inj = rep["injection_smoke"]
    lines.append(
        f"  Injection smoke (synthetic doc): {'PASS' if inj['passed'] else 'FAIL'} {'' if inj['passed'] else inj}"
    )
    lines.append("  Gates: " + ", ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in rep["gates"].items()))
    return "\n".join(lines)


def write_report(rep: dict[str, Any], out: Path = REPORT) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    first = out.parent / "report_first_run.json"
    if not first.exists():
        shutil.copyfile(out, first)
