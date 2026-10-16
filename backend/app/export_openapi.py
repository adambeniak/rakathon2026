"""Print the OpenAPI document to stdout with stable ordering: `python -m app.export_openapi > contracts/openapi.json`.

Use `make contract` (writes via a temp file and regenerates the TS client). CI fails if the committed contract differs.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from app.main import create_app
from app.settings import Settings


def stable_json(document: dict[str, Any]) -> str:
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    app = create_app(Settings(_env_file=None, log_level="WARNING"))
    sys.stdout.buffer.write(stable_json(app.openapi()).encode("utf-8"))


if __name__ == "__main__":
    main()
