"""Open Finance Brasil public Directory and Portal routes."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from findata.sources.openfinance import directory as of_dir
from findata.sources.openfinance import portal as of_portal

router = APIRouter(prefix="/openfinance", tags=["Open Finance Brasil"])


@router.get("/resources")
async def resources(
    environment: of_dir.Environment = Query(default="production"),
) -> list[of_dir.OpenFinanceDirectoryResource]:
    """List public Open Finance Directory resources supported by findata-br."""
    return of_dir.public_resources(environment)


@router.get("/participants")
async def participants(
    environment: of_dir.Environment = Query(default="production"),
    role: str | None = Query(default=None, description="Filter by Directory role, e.g. DADOS"),
    status: str | None = Query(
        default="Active",
        description="Participant status; set empty for all",
    ),
    api_family: str | None = Query(default=None, description="Filter by API family substring"),
    q: str | None = Query(
        default=None,
        min_length=2,
        max_length=128,
        description="Name/CNPJ substring",
    ),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[of_dir.OpenFinanceParticipantSummary]:
    """List Open Finance participants as compact summaries."""
    raw = await of_dir.get_participants(environment)
    filtered = of_dir.filter_participants(
        raw,
        role=role,
        status=status or None,
        api_family=api_family,
        query=q,
    )
    return of_dir.summarise_participants(filtered[:limit])


@router.get("/participants/raw")
async def participants_raw(
    environment: of_dir.Environment = Query(default="production"),
    role: str | None = Query(default=None),
    status: str | None = Query(default="Active"),
    api_family: str | None = Query(default=None),
    q: str | None = Query(default=None, min_length=2, max_length=128),
    limit: int = Query(default=25, ge=1, le=250),
) -> list[dict[str, object]]:
    """Return raw public participant records from the Directory."""
    raw = await of_dir.get_participants(environment)
    filtered = of_dir.filter_participants(
        raw,
        role=role,
        status=status or None,
        api_family=api_family,
        query=q,
    )
    return filtered[:limit]


@router.get("/participants/{organisation_id}")
async def participant(
    organisation_id: str,
    environment: of_dir.Environment = Query(default="production"),
) -> dict[str, object]:
    """Return one raw participant by OrganisationId."""
    item = await of_dir.find_participant(organisation_id, environment)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Unknown OrganisationId: {organisation_id}")
    return item


@router.get("/endpoints")
async def endpoints(
    environment: of_dir.Environment = Query(default="production"),
    api_family: str | None = Query(default=None, description="API family substring"),
    status: str | None = Query(
        default="Active",
        description="Participant status; set empty for all",
    ),
    limit: int = Query(default=200, ge=1, le=5000),
) -> list[of_dir.OpenFinanceApiEndpoint]:
    """Flatten API discovery endpoints advertised in public `/participants`."""
    raw = await of_dir.get_participants(environment)
    return of_dir.flatten_api_endpoints(raw, api_family=api_family, status=status or None)[:limit]


@router.get("/directory/roles")
async def roles(
    environment: of_dir.Environment = Query(default="production"),
    limit: int = Query(default=1000, ge=1, le=5000),
) -> list[dict[str, object]]:
    """Return public Directory roles."""
    return (await of_dir.get_roles(environment))[:limit]


@router.get("/directory/api-resources")
async def api_resources(
    environment: of_dir.Environment = Query(default="production"),
) -> list[dict[str, object]]:
    """Return public API-resource definitions publishable in the ecosystem."""
    return await of_dir.get_api_resources(environment)


@router.get("/directory/well-known")
async def well_known(
    environment: of_dir.Environment = Query(default="production"),
) -> dict[str, object]:
    """Return public OIDC discovery metadata for the Directory issuer."""
    return await of_dir.get_well_known(environment)


@router.get("/directory/keystore")
async def directory_keystore(
    environment: of_dir.Environment = Query(default="production"),
) -> dict[str, object]:
    """Return public Directory JWKS."""
    return await of_dir.get_directory_keystore(environment)


@router.get("/directory/organisations/{organisation_id}/application-jwks")
async def organisation_application_jwks(
    organisation_id: str,
    environment: of_dir.Environment = Query(default="production"),
) -> dict[str, object]:
    """Return public organization-level signing keys."""
    return await of_dir.get_organisation_application_jwks(organisation_id, environment)


@router.get("/directory/software/{organisation_id}/{software_statement_id}/transport-jwks")
async def software_transport_jwks(
    organisation_id: str,
    software_statement_id: str,
    environment: of_dir.Environment = Query(default="production"),
) -> dict[str, object]:
    """Return public software-level transport-certificate keys."""
    return await of_dir.get_software_transport_jwks(
        organisation_id,
        software_statement_id,
        environment,
    )


@router.get("/directory/software/{organisation_id}/{software_statement_id}/application-jwks")
async def software_application_jwks(
    organisation_id: str,
    software_statement_id: str,
    environment: of_dir.Environment = Query(default="production"),
) -> dict[str, object]:
    """Return public software-level signing keys."""
    return await of_dir.get_software_application_jwks(
        organisation_id,
        software_statement_id,
        environment,
    )


@router.get("/portal/datasets")
async def portal_datasets() -> list[of_portal.OpenFinancePortalDataset]:
    """List public Open Finance Portal datasets supported by findata-br."""
    return of_portal.list_datasets()


@router.get("/portal/datasets/{slug}/files")
async def portal_dataset_files(
    slug: str,
    page: int = Query(default=1, ge=1, le=20),
) -> list[of_portal.OpenFinancePortalFile]:
    """List downloadable files for a public Portal dataset page."""
    return await of_portal.get_dataset_files(slug, page)


@router.get("/portal/download/{download_id}")
async def portal_download(download_id: str) -> StreamingResponse:
    """Download one public Portal file by id."""
    filename = of_portal.download_filename(download_id)

    async def _body() -> AsyncIterator[bytes]:
        async with of_portal.stream_download_file(download_id) as chunks:
            async for chunk in chunks:
                yield chunk

    return StreamingResponse(
        _body(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
