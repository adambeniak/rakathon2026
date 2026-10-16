"""NormalizedDoc -> chunks for vector search (owner: P2; used by app.retrieval.indexing).

Paragraph-aware: chunks are packed from whole blocks. A paragraph that does not fit is cut at sentence boundaries,
and a sentence that does not fit at word boundaries. A table row ("tr" block) is NEVER split; a row that does not
fit on its own becomes its own oversized chunk. Consecutive chunks overlap by up to `overlap` characters, starting
on a word boundary and never inside a table row.

Size is measured by `measure` (default: characters). The local embedder passes a token counter for the text it
actually embeds, so every chunk fits the model's 128-token window (docs/vector-search.md).

Invariant: `chunk.text == doc.text[chunk.char_start:chunk.char_end]`. A quote found in a chunk is therefore also
found in the document, and the UI can highlight it by offsets.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.documents.normalize import NormalizedDoc

DEFAULT_MAX_CHARS = 800
DEFAULT_OVERLAP = 100

# Sentence end followed by an upper-case letter: keeps Czech dates ("12. 10. 2026") and "st. p." together.
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ])")

Measure = Callable[[str], int]


@dataclass(frozen=True)
class Chunk:
    seq: int
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class _Unit:
    start: int
    end: int
    splittable: bool  # False for table rows: overlap may only start at their first character


class _Fit:
    def __init__(self, text: str, measure: Measure, max_size: int) -> None:
        self.text = text
        self.measure = measure
        self.max_size = max_size

    def __call__(self, start: int, end: int) -> bool:
        return self.measure(self.text[start:end]) <= self.max_size


def _split_long(fits: _Fit, start: int, end: int) -> list[_Unit]:
    """Sentences of text[start:end]; a sentence that does not fit is cut at the last space that fits."""
    text = fits.text
    pieces: list[tuple[int, int]] = []
    pos = start
    for m in _SENTENCE_END.finditer(text, start, end):
        pieces.append((pos, m.start()))
        pos = m.end()
    pieces.append((pos, end))

    units: list[_Unit] = []
    for s, e in pieces:
        while not fits(s, e):
            spaces = [i for i in range(s + 1, e) if text[i] == " "]
            cut = next((i for i in reversed(spaces) if fits(s, i)), spaces[0] if spaces else e)
            units.append(_Unit(s, cut, True))
            if cut >= e:
                break
            s = cut + 1
        else:
            units.append(_Unit(s, e, True))
    return units


def _units(doc: NormalizedDoc, fits: _Fit) -> list[_Unit]:
    units: list[_Unit] = []
    for block in doc.blocks:
        if block.kind == "tr":
            units.append(_Unit(block.start, block.end, False))
        elif fits(block.start, block.end):
            units.append(_Unit(block.start, block.end, True))
        else:
            units.extend(_split_long(fits, block.start, block.end))
    return units


def _overlap_start(text: str, units: list[_Unit], chunk_start: int, chunk_end: int, overlap: int) -> int | None:
    """Earliest allowed boundary in (chunk_start, chunk_end) at most `overlap` chars before chunk_end.

    Allowed boundaries: the start of any unit, and word starts inside splittable units (never inside a table row).
    """
    lower = max(chunk_end - overlap, chunk_start + 1)
    best: int | None = None
    for unit in units:
        if unit.end <= lower or unit.start >= chunk_end:
            continue
        if unit.start >= lower:
            candidate: int | None = unit.start
        elif unit.splittable:
            space = text.find(" ", lower - 1, unit.end)
            candidate = space + 1 if space >= 0 and space + 1 < min(unit.end, chunk_end) else None
        else:
            candidate = None
        if candidate is not None and (best is None or candidate < best):
            best = candidate
    return best


def chunk_document(
    doc: NormalizedDoc,
    *,
    max_size: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
    measure: Measure = len,
) -> list[Chunk]:
    """Chunks of at most `max_size` (in `measure` units); `overlap` is in characters."""
    if max_size < 16 or overlap < 0:
        raise ValueError("need max_size >= 16 and overlap >= 0")
    fits = _Fit(doc.text, measure, max_size)
    units = _units(doc, fits)
    spans: list[tuple[int, int]] = []
    start: int | None = None
    end = 0
    for unit in units:
        if start is None:
            start, end = unit.start, unit.end
            continue
        if fits(start, unit.end):
            end = unit.end
            continue
        spans.append((start, end))
        carried = _overlap_start(doc.text, units, start, end, overlap) if overlap else None
        start = carried if carried is not None and fits(carried, unit.end) else unit.start
        end = unit.end
    if start is not None:
        spans.append((start, end))
    return [Chunk(seq, doc.text[s:e], s, e) for seq, (s, e) in enumerate(spans)]
