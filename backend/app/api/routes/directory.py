"""GET /api/directory/kocs: the KOC list for the referral form (mCSD-like: name, city, coordinator contact)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ActorDep, DirectoryProviderDep
from app.api.schemas.common import problem_responses
from app.api.schemas.directory import CoordinatorContact, KocEntry
from app.domain.common import Role

router = APIRouter(prefix="/directory", tags=["directory"])


@router.get(
    "/kocs",
    response_model=list[KocEntry],
    summary="List KOCs with their coordinator contact",
    responses=problem_responses(401, 502, 503),
)
async def list_kocs(provider: DirectoryProviderDep, _actor: ActorDep) -> list[KocEntry]:
    directory = await provider.get()
    result: list[KocEntry] = []
    for entry in directory.kocs():
        holder = directory.role_holder(entry.org.id, Role.COORDINATOR)
        result.append(
            KocEntry(
                id=entry.org.id,
                name=entry.org.name,
                city=entry.org.address.city if entry.org.address else None,
                coordinator=CoordinatorContact(id=holder.id, display=holder.display, phone=entry.org.phone)
                if holder
                else None,
            )
        )
    return result
