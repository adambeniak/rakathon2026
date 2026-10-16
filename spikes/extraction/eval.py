# /// script
# requires-python = ">=3.12"
# dependencies = ["python-docx==1.2.0", "pydantic==2.11.7", "openai==1.99.9"]
# ///
"""Extraction eval vs the golden set.

    uv run spikes/extraction/eval.py                     # cache only (STAFETA_LLM_CACHE=1 default)
    STAFETA_LLM_CACHE=0 uv run --env-file .env spikes/extraction/eval.py   # fill the cache via APIM

Writes eval/report.json (repo root); the very first run is also kept as eval/report_first_run.json.
Exit code 1 when a hard gate fails (evidence validity 100 %, hallucinations 0, as-of leakage 0).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from documents import NormalizedDoc, match_key, normalize, normalize_text  # noqa: E402
from extraction import PS_CUE, DocExtraction, extract_facts, filter_as_of, stated_with_negation_cue  # noqa: E402
from golden_atoms import build_atoms, coverage_items, text_coverage  # noqa: E402
from injection import injection_smoke  # noqa: E402
from llm import LLMClient  # noqa: E402
from prompt import PROMPT_VERSION  # noqa: E402
from schema import DateValue, Fact, QuantityValue  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "data" / "golden" / "expected_handover_2026-10-21.json"
DOCS_DIR = REPO / "data" / "raw" / "Pacient"
DEFAULT_AS_OF = "2026-10-21T08:00:00+02:00"
RECALL_TARGET = 0.90


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# ---------------------------------------------------------------- independent audits (do not reuse the lock code)


def _independent_quote_ok(fact: Fact, fresh: NormalizedDoc) -> bool:
    if fresh.text[fact.span[0] : fact.span[1]] != fact.quote:
        return False
    return " ".join(fact.quote.split()) in " ".join(fresh.text.split())


def _value_tokens_ok(fact: Fact) -> list[str]:
    """Every digit run in the value must occur in the quote (NFKC, comma/point agnostic)."""
    quote = unicodedata.normalize("NFKC", fact.quote).replace(",", ".")
    problems: list[str] = []
    v = fact.value
    texts: list[str] = []
    for k, item in v.model_dump().items():
        if k in {"kind", "system", "flag", "comparator", "number"} or isinstance(v, DateValue):
            continue
        if isinstance(item, str):
            texts.append(item)
    if isinstance(v, QuantityValue) and v.number is not None:
        n = v.number
        texts.append(str(int(n)) if float(n).is_integer() else repr(n))
    for t in texts:
        t = re.sub(r"\b\d{4}-\d{2}(-\d{2})?\b", " ", unicodedata.normalize("NFKC", t)).replace(",", ".")
        for tok in re.findall(r"\d+(?:\.\d+)?", t):
            variants = {tok, tok.rstrip("0").rstrip(".") if "." in tok else tok}
            if not any(re.search(rf"(?<![\d.]){re.escape(x)}(?![\d])", quote) for x in variants):
                problems.append(tok)
    return problems


# ---------------------------------------------------------------- main


async def run(as_of: datetime, model: str) -> dict[str, Any]:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    paths = sorted(DOCS_DIR.glob("*.docx"))
    docs = {p.stem: normalize(p) for p in paths}
    client = LLMClient(model=model, prompt_version=PROMPT_VERSION)
    results: list[DocExtraction] = await asyncio.gather(*(extract_facts(d, client) for d in docs.values()))
    injection = await injection_smoke(client)

    raw_total = sum(len(r.raw) for r in results)
    raw_exact = 0
    for r in results:
        key = match_key(docs[r.doc_id].text).key
        raw_exact += sum(1 for f in r.raw if match_key(normalize_text(f.quote)).key in key)
    accepted_all = [f for r in results for f in r.accepted]
    final = filter_as_of(accepted_all, docs, as_of)
    excluded = {e["doc"] for e in golden["excluded_documents"]}
    included_golden = set(golden["included_documents"])
    included_run = {d for d in docs if any(f.doc_id == d for f in final)} | {d for d in docs if d in included_golden}

    # evidence validity: re-normalise from DOCX independently
    fresh = {p.stem: normalize(p) for p in paths}
    invalid = [f for f in final if not _independent_quote_ok(f, fresh[f.doc_id])]

    # hallucination audit
    halluc: list[dict[str, Any]] = []
    for f in final:
        probs = _value_tokens_ok(f)
        if probs:
            halluc.append({"fact_id": f.fact_id, "doc": f.doc_id, "why": f"value numbers not in quote: {probs}"})
        if f.type == "performance_status" and not PS_CUE.search(f.quote):
            halluc.append({"fact_id": f.fact_id, "doc": f.doc_id, "why": "PS without ECOG/Karnofsky"})
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
            "repaired_quotes": sum(1 for f in accepted_all if f.repaired),
            "facts_in_handover": len(final),
            "evidence_validity": round(1 - len(invalid) / len(final), 4) if final else None,
            "hallucinations": len(halluc),
            "as_of_leakage": len(leakage),
            "excluded_doc_facts_filtered": excluded_extracted,
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
            {"doc": f.doc_id, "type": f.type, "quote": f.quote[:120]} for f in final if stated_with_negation_cue(f)
        ],
        "per_document": per_doc,
        "facts": [f.model_dump(mode="json") for f in final],
    }


def print_table(rep: dict[str, Any]) -> None:
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
        ("Stated with negation cue", m["stated_with_negation_cue"], "audit"),
    ]
    print(f"Štafeta extraction eval · {rep['model']} · {rep['prompt_version']} · commit {rep['commit']}")
    for name, val, note in rows:
        print(f"  {name:<34} {val!s:<22} {note}")
    print("  Rejections:", rep["rejections_by_reason"] or "none")
    if rep["misses"]:
        print("  Misses:")
        for miss in rep["misses"]:
            print(f"    - {miss['atom']}: {miss['expected']}")
    for h in rep["hallucination_details"]:
        print(f"  HALLUCINATION: {h}")
    inj = rep["injection_smoke"]
    print(
        f"  Injection smoke (synthetic doc): {'PASS' if inj['passed'] else 'FAIL'} {inj if not inj['passed'] else ''}"
    )
    print("  Gates:", ", ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in rep["gates"].items()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=DEFAULT_AS_OF)
    ap.add_argument("--model", default=os.environ.get("LLM_MODEL_EXTRACT", "gpt-6-1-sol-dz-eu"))
    ap.add_argument("--out", default=str(REPO / "eval" / "report.json"))
    args = ap.parse_args()
    rep = asyncio.run(run(datetime.fromisoformat(args.as_of), args.model))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    first = out.parent / "report_first_run.json"
    if not first.exists():
        shutil.copyfile(out, first)
    print_table(rep)
    return 0 if all(rep["gates"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
