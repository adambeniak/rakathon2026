"""Print the handover JSON Schema to stdout: `python -m app.export_schemas > contracts/handover.schema.json`.

Generated from `app.domain.handover.Handover`, so the contract and the code cannot drift (CI diffs it).
"""

from __future__ import annotations

import sys

from app.domain.handover import Handover
from app.export_openapi import stable_json

SCHEMA_ID = "https://stafeta.example/contracts/handover.schema.json"


def handover_schema() -> dict[str, object]:
    schema = Handover.model_json_schema(by_alias=True, mode="serialization")
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": SCHEMA_ID, **schema}


def main() -> None:
    sys.stdout.buffer.write(stable_json(handover_schema()).encode("utf-8"))


if __name__ == "__main__":
    main()
