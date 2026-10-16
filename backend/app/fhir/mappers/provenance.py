"""Provenance of a launched pathway: the coordinator created the orders on behalf of the indicating physician."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from app.domain.common import PartyRef
from app.fhir.client import Resource
from app.fhir.systems import PROVENANCE_PARTICIPANT_TYPE, SID_PRACTITIONER_ROLE, V3_DATA_OPERATION


def pathway_launch_provenance(
    *, targets: Sequence[str], coordinator: PartyRef, indicating: Resource, recorded: datetime
) -> Resource:
    """`targets` are the CarePlan and the ServiceRequests; `indicating` is a Reference to the physician's role."""
    return {
        "resourceType": "Provenance",
        "target": [{"reference": reference} for reference in targets],
        "recorded": recorded.isoformat(),
        "activity": {"coding": [{"system": V3_DATA_OPERATION, "code": "CREATE"}]},
        "agent": [
            {
                "type": {"coding": [{"system": PROVENANCE_PARTICIPANT_TYPE, "code": "author"}]},
                "who": {
                    "identifier": {"system": SID_PRACTITIONER_ROLE, "value": coordinator.id},
                    "display": coordinator.display,
                },
                "onBehalfOf": indicating,
            }
        ],
    }
