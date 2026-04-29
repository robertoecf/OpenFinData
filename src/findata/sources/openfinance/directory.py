"""Open Finance Brasil public Directory resources.

Track A only: public discovery metadata from the Open Finance Brasil
Directory. This module deliberately does not implement consented customer-data
flows, Dynamic Client Registration, mTLS, private keys, or FAPI relying-party
certification.
"""

from __future__ import annotations

import re
from typing import Any, Literal, cast
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

from findata.http_client import get_json

Environment = Literal["production", "sandbox"]

_DATA_BASE: dict[Environment, str] = {
    "production": "https://data.directory.openbankingbrasil.org.br",
    "sandbox": "https://data.sandbox.directory.openbankingbrasil.org.br",
}
_WEB_BASE: dict[Environment, str] = {
    "production": "https://web.directory.openbankingbrasil.org.br",
    "sandbox": "https://web.sandbox.directory.openbankingbrasil.org.br",
}
_AUTH_BASE: dict[Environment, str] = {
    "production": "https://auth.directory.openbankingbrasil.org.br",
    "sandbox": "https://auth.sandbox.directory.openbankingbrasil.org.br",
}
_KEYSTORE_BASE: dict[Environment, str] = {
    "production": "https://keystore.directory.openbankingbrasil.org.br",
    "sandbox": "https://keystore.sandbox.directory.openbankingbrasil.org.br",
}

PUBLIC_CACHE_TTL = 900  # Directory guidance: /participants refreshes every 15 min.
STATIC_CACHE_TTL = 86400
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


class OpenFinanceParticipantSummary(BaseModel):
    """Compact, stable summary of a Directory participant."""

    model_config = ConfigDict(extra="forbid")

    organisation_id: str
    organisation_name: str | None = None
    registered_name: str | None = None
    registration_number: str | None = None
    status: str | None = None
    roles: list[str]
    authorization_servers: int
    api_resources: int


class OpenFinanceApiEndpoint(BaseModel):
    """Flattened API endpoint advertised by a participant authorization server."""

    model_config = ConfigDict(extra="forbid")

    organisation_id: str
    organisation_name: str | None = None
    registration_number: str | None = None
    authorisation_server_id: str | None = None
    authorisation_server_name: str | None = None
    developer_portal_uri: str | None = None
    api_resource_id: str | None = None
    api_family_type: str | None = None
    api_version: str | None = None
    api_status: str | None = None
    certification_status: str | None = None
    api_endpoint: str


class OpenFinanceDirectoryResource(BaseModel):
    """Named public resource exposed by the Open Finance Directory."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    url: str
    environment: Environment
    auth: Literal["none"] = "none"
    cache_ttl_seconds: int


def _data_base(environment: Environment) -> str:
    """Return the public data API base URL for one Directory environment."""
    return _DATA_BASE[environment]


def _web_base(environment: Environment) -> str:
    """Return the web API base URL for one Directory environment."""
    return _WEB_BASE[environment]


def _auth_base(environment: Environment) -> str:
    """Return the OIDC issuer base URL for one Directory environment."""
    return _AUTH_BASE[environment]


def _keystore_base(environment: Environment) -> str:
    """Return the Directory keystore base URL for one environment."""
    return _KEYSTORE_BASE[environment]


def _dicts(value: object) -> list[dict[str, Any]]:
    """Return only dict items when the input is a list."""
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], item) for item in value if isinstance(item, dict)]


def _str_or_none(value: object) -> str | None:
    """Return a non-empty string value, otherwise None."""
    return value if isinstance(value, str) and value else None


def _str_value(value: object) -> str:
    """Return an object as a string, treating None as an empty value."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _matches(value: str | None, needle: str | None) -> bool:
    """Return whether a nullable string contains a nullable casefolded needle."""
    if needle is None:
        return True
    if value is None:
        return False
    return needle.casefold() in value.casefold()


def _is_active_status(value: object) -> bool:
    """Treat missing status and case-insensitive 'active' as active."""
    status = _str_or_none(value)
    return status is None or status.casefold() == "active"


def _safe_uuid(value: str, field: str) -> str:
    """Validate and URL-quote a UUID path segment."""
    if not _UUID_RE.fullmatch(value):
        raise ValueError(f"invalid Open Finance {field}: expected UUID")
    return quote(value, safe="")


async def get_participants(environment: Environment = "production") -> list[dict[str, Any]]:
    """Return raw public participants from the Directory `/participants` endpoint."""
    raw = await get_json(f"{_data_base(environment)}/participants", cache_ttl=PUBLIC_CACHE_TTL)
    participants = _dicts(raw)
    if not participants and raw != []:
        raise ValueError("unexpected Open Finance participants response shape")
    return participants


async def get_roles(environment: Environment = "production") -> list[dict[str, Any]]:
    """Return public Directory roles."""
    raw = await get_json(f"{_data_base(environment)}/roles", cache_ttl=PUBLIC_CACHE_TTL)
    roles = _dicts(raw)
    if not roles and raw != []:
        raise ValueError("unexpected Open Finance roles response shape")
    return roles


async def get_api_resources(environment: Environment = "production") -> list[dict[str, Any]]:
    """Return the public catalog of API resources publishable in the ecosystem."""
    raw = await get_json(
        f"{_web_base(environment)}/config/apiresources",
        cache_ttl=PUBLIC_CACHE_TTL,
    )
    resources = _dicts(raw)
    if not resources and raw != []:
        raise ValueError("unexpected Open Finance API resources response shape")
    return resources


async def get_well_known(environment: Environment = "production") -> dict[str, Any]:
    """Return the public OIDC discovery document for the Directory."""
    raw = await get_json(
        f"{_auth_base(environment)}/.well-known/openid-configuration",
        cache_ttl=STATIC_CACHE_TTL,
    )
    if not isinstance(raw, dict):
        raise ValueError("unexpected Open Finance well-known response shape")
    return cast(dict[str, Any], raw)


async def get_directory_keystore(environment: Environment = "production") -> dict[str, Any]:
    """Return the public Directory keystore used to verify Directory signatures."""
    raw = await get_json(_keystore_base(environment), cache_ttl=STATIC_CACHE_TTL)
    if not isinstance(raw, dict):
        raise ValueError("unexpected Open Finance keystore response shape")
    return cast(dict[str, Any], raw)


async def get_organisation_application_jwks(
    organisation_id: str,
    environment: Environment = "production",
) -> dict[str, Any]:
    """Return public organization-level signing keys for an Open Finance participant."""
    org_id = _safe_uuid(organisation_id, "organisation_id")
    raw = await get_json(
        f"{_web_base(environment)}/{org_id}/application.jwks",
        cache_ttl=STATIC_CACHE_TTL,
    )
    if not isinstance(raw, dict):
        raise ValueError("unexpected Open Finance organisation JWKS response shape")
    return cast(dict[str, Any], raw)


async def get_software_transport_jwks(
    organisation_id: str,
    software_statement_id: str,
    environment: Environment = "production",
) -> dict[str, Any]:
    """Return public software-level transport-certificate keys."""
    org_id = _safe_uuid(organisation_id, "organisation_id")
    software_id = _safe_uuid(software_statement_id, "software_statement_id")
    raw = await get_json(
        f"{_web_base(environment)}/{org_id}/{software_id}/transport.jwks",
        cache_ttl=STATIC_CACHE_TTL,
    )
    if not isinstance(raw, dict):
        raise ValueError("unexpected Open Finance transport JWKS response shape")
    return cast(dict[str, Any], raw)


async def get_software_application_jwks(
    organisation_id: str,
    software_statement_id: str,
    environment: Environment = "production",
) -> dict[str, Any]:
    """Return public software-level signing keys."""
    org_id = _safe_uuid(organisation_id, "organisation_id")
    software_id = _safe_uuid(software_statement_id, "software_statement_id")
    raw = await get_json(
        f"{_web_base(environment)}/{org_id}/{software_id}/application.jwks",
        cache_ttl=STATIC_CACHE_TTL,
    )
    if not isinstance(raw, dict):
        raise ValueError("unexpected Open Finance application JWKS response shape")
    return cast(dict[str, Any], raw)


def public_resources(environment: Environment = "production") -> list[OpenFinanceDirectoryResource]:
    """List the public Directory resources this adapter supports."""
    data = _data_base(environment)
    web = _web_base(environment)
    auth = _auth_base(environment)
    keystore = _keystore_base(environment)
    return [
        OpenFinanceDirectoryResource(
            name="participants",
            description=(
                "Participants, authorization servers, API resources and endpoint discovery."
            ),
            url=f"{data}/participants",
            environment=environment,
            cache_ttl_seconds=PUBLIC_CACHE_TTL,
        ),
        OpenFinanceDirectoryResource(
            name="roles",
            description="Public role assignments in the Open Finance ecosystem.",
            url=f"{data}/roles",
            environment=environment,
            cache_ttl_seconds=PUBLIC_CACHE_TTL,
        ),
        OpenFinanceDirectoryResource(
            name="apiresources",
            description="Public catalog of API family types, versions and expected URL structures.",
            url=f"{web}/config/apiresources",
            environment=environment,
            cache_ttl_seconds=PUBLIC_CACHE_TTL,
        ),
        OpenFinanceDirectoryResource(
            name="well-known",
            description="OIDC discovery metadata for the Directory issuer.",
            url=f"{auth}/.well-known/openid-configuration",
            environment=environment,
            cache_ttl_seconds=STATIC_CACHE_TTL,
        ),
        OpenFinanceDirectoryResource(
            name="directory-keystore",
            description="Directory JWKS used to verify Directory-signed metadata.",
            url=keystore,
            environment=environment,
            cache_ttl_seconds=STATIC_CACHE_TTL,
        ),
        OpenFinanceDirectoryResource(
            name="organisation-application-jwks",
            description=(
                "Organization-level public signing keys: "
                "/{organisationId}/application.jwks."
            ),
            url=f"{web}/{{organisationId}}/application.jwks",
            environment=environment,
            cache_ttl_seconds=STATIC_CACHE_TTL,
        ),
        OpenFinanceDirectoryResource(
            name="software-transport-jwks",
            description=(
                "Software-level public transport keys: "
                "/{organisationId}/{softwareStatementId}/transport.jwks."
            ),
            url=f"{web}/{{organisationId}}/{{softwareStatementId}}/transport.jwks",
            environment=environment,
            cache_ttl_seconds=STATIC_CACHE_TTL,
        ),
        OpenFinanceDirectoryResource(
            name="software-application-jwks",
            description=(
                "Software-level public signing keys: "
                "/{organisationId}/{softwareStatementId}/application.jwks."
            ),
            url=f"{web}/{{organisationId}}/{{softwareStatementId}}/application.jwks",
            environment=environment,
            cache_ttl_seconds=STATIC_CACHE_TTL,
        ),
    ]


def summarise_participant(item: dict[str, Any]) -> OpenFinanceParticipantSummary:
    """Normalize one raw participant record into a compact summary."""
    servers = _dicts(item.get("AuthorisationServers"))
    role_claims = _dicts(item.get("OrgDomainRoleClaims"))
    roles: list[str] = []
    for claim in role_claims:
        role = _str_or_none(claim.get("Role"))
        if role and _is_active_status(claim.get("Status")):
            roles.append(role)

    api_resources = 0
    for server in servers:
        api_resources += len(_dicts(server.get("ApiResources")))

    return OpenFinanceParticipantSummary(
        organisation_id=_str_value(item.get("OrganisationId")),
        organisation_name=_str_or_none(item.get("OrganisationName")),
        registered_name=_str_or_none(item.get("RegisteredName")),
        registration_number=_str_or_none(item.get("RegistrationNumber")),
        status=_str_or_none(item.get("Status")),
        roles=sorted(set(roles)),
        authorization_servers=len(servers),
        api_resources=api_resources,
    )


def filter_participants(
    participants: list[dict[str, Any]],
    *,
    role: str | None = None,
    status: str | None = "Active",
    api_family: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Filter raw participants by public metadata."""
    results: list[dict[str, Any]] = []
    role_cf = role.casefold() if role else None
    status_cf = status.casefold() if status else None
    api_family_cf = api_family.casefold() if api_family else None
    query_cf = query.casefold() if query else None

    for item in participants:
        if status_cf and _str_value(item.get("Status")).casefold() != status_cf:
            continue
        if query_cf:
            haystack = " ".join(
                filter(
                    None,
                    [
                        _str_or_none(item.get("OrganisationName")),
                        _str_or_none(item.get("RegisteredName")),
                        _str_or_none(item.get("RegistrationNumber")),
                    ],
                )
            ).casefold()
            if query_cf not in haystack:
                continue
        if role_cf:
            role_claims = _dicts(item.get("OrgDomainRoleClaims"))
            roles = [
                _str_value(claim.get("Role")).casefold()
                for claim in role_claims
                if _is_active_status(claim.get("Status"))
            ]
            if role_cf not in roles:
                continue
        if api_family_cf:
            endpoints = flatten_api_endpoints(
                [item],
                api_family=api_family,
                status=status,
            )
            if not endpoints:
                continue
        results.append(item)
    return results


def summarise_participants(
    participants: list[dict[str, Any]],
) -> list[OpenFinanceParticipantSummary]:
    """Normalize a participant list into compact summaries."""
    return [summarise_participant(item) for item in participants]


def flatten_api_endpoints(
    participants: list[dict[str, Any]],
    *,
    api_family: str | None = None,
    status: str | None = "Active",
) -> list[OpenFinanceApiEndpoint]:
    """Flatten all API discovery endpoints advertised in `/participants`."""
    results: list[OpenFinanceApiEndpoint] = []
    for org in participants:
        org_status = _str_value(org.get("Status"))
        if status and org_status.casefold() != status.casefold():
            continue
        organisation_id = _str_value(org.get("OrganisationId"))
        organisation_name = _str_or_none(org.get("OrganisationName"))
        registration_number = _str_or_none(org.get("RegistrationNumber"))
        for server in _dicts(org.get("AuthorisationServers")):
            server_id = _str_or_none(server.get("AuthorisationServerId"))
            server_name = _str_or_none(server.get("CustomerFriendlyName"))
            developer_portal = _str_or_none(server.get("DeveloperPortalUri"))
            for resource in _dicts(server.get("ApiResources")):
                family = _str_or_none(resource.get("ApiFamilyType"))
                if not _matches(family, api_family):
                    continue
                version = _str_or_none(resource.get("ApiVersion")) or _str_value(
                    resource.get("ApiVersion")
                )
                api_resource_id = _str_or_none(resource.get("ApiResourceId"))
                api_status = _str_or_none(resource.get("Status"))
                certification = _str_or_none(resource.get("CertificationStatus"))
                for endpoint in _dicts(resource.get("ApiDiscoveryEndpoints")):
                    api_endpoint = _str_or_none(endpoint.get("ApiEndpoint"))
                    if not api_endpoint:
                        continue
                    results.append(
                        OpenFinanceApiEndpoint(
                            organisation_id=organisation_id,
                            organisation_name=organisation_name,
                            registration_number=registration_number,
                            authorisation_server_id=server_id,
                            authorisation_server_name=server_name,
                            developer_portal_uri=developer_portal,
                            api_resource_id=api_resource_id,
                            api_family_type=family,
                            api_version=version or None,
                            api_status=api_status,
                            certification_status=certification,
                            api_endpoint=api_endpoint,
                        )
                    )
    return results


async def find_participant(
    organisation_id: str,
    environment: Environment = "production",
) -> dict[str, Any] | None:
    """Find one raw participant by OrganisationId."""
    needle = organisation_id.casefold()
    for item in await get_participants(environment):
        if _str_value(item.get("OrganisationId")).casefold() == needle:
            return item
    return None
