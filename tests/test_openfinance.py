"""Open Finance Brasil public Track A tests (no network; respx-mocked)."""

from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from findata.api.app import app
from findata.http_client import clear_cache
from findata.sources.openfinance import directory as of_dir
from findata.sources.openfinance import portal as of_portal

PARTICIPANTS_URL = "https://data.directory.openbankingbrasil.org.br/participants"
ROLES_URL = "https://data.directory.openbankingbrasil.org.br/roles"
API_RESOURCES_URL = "https://web.directory.openbankingbrasil.org.br/config/apiresources"
WELL_KNOWN_URL = "https://auth.directory.openbankingbrasil.org.br/.well-known/openid-configuration"
KEYSTORE_URL = "https://keystore.directory.openbankingbrasil.org.br"

PARTICIPANTS = [
    {
        "OrganisationId": "org-1",
        "Status": "Active",
        "OrganisationName": "Banco Exemplo",
        "RegisteredName": "BANCO EXEMPLO S.A.",
        "RegistrationNumber": "00000000000100",
        "OrgDomainRoleClaims": [
            {"Role": "DADOS", "Status": "Active"},
            {"Role": "PAGTO", "Status": "Inactive"},
        ],
        "AuthorisationServers": [
            {
                "AuthorisationServerId": "as-1",
                "CustomerFriendlyName": "Banco Exemplo",
                "DeveloperPortalUri": "https://developer.example.test",
                "ApiResources": [
                    {
                        "ApiResourceId": "res-1",
                        "ApiFamilyType": "channels",
                        "ApiVersion": "1.0.0",
                        "Status": "Active",
                        "CertificationStatus": "Self-Certified",
                        "ApiDiscoveryEndpoints": [
                            {
                                "ApiDiscoveryId": "disc-1",
                                "ApiEndpoint": "https://api.example.test/open-banking/channels/v1/branches",
                            }
                        ],
                    }
                ],
            }
        ],
    },
    {
        "OrganisationId": "org-2",
        "Status": "Active",
        "OrganisationName": "Instituição Sem Canais",
        "RegisteredName": "INSTITUICAO SEM CANAIS LTDA",
        "RegistrationNumber": "11111111000100",
        "OrgDomainRoleClaims": [{"Role": "PAGTO", "Status": "Active"}],
        "AuthorisationServers": [],
    },
]

PORTAL_HTML = """
<html>
  <a href="/api/download?id=51b0a27a-a295-43c4-b275-53c010e6ced1">Download</a>
  <script>
    self.__next_f.push(["children":"CSV"]);
    self.__next_f.push(["children":"Consolidado Agosto 2025"]);
    self.__next_f.push(["children":"Dados de 26/07/2025 a 29/08/2025"]);
  </script>
</html>
"""


def test_directory_flatten_and_filter_participants() -> None:
    filtered = of_dir.filter_participants(PARTICIPANTS, role="DADOS", api_family="channels")
    assert len(filtered) == 1

    summary = of_dir.summarise_participant(filtered[0])
    assert summary.organisation_id == "org-1"
    assert summary.roles == ["DADOS"]
    assert summary.authorization_servers == 1
    assert summary.api_resources == 1

    endpoints = of_dir.flatten_api_endpoints(PARTICIPANTS, api_family="channels")
    assert len(endpoints) == 1
    assert endpoints[0].api_family_type == "channels"
    assert endpoints[0].api_endpoint.endswith("/branches")


def test_portal_parse_dataset_files() -> None:
    files = of_portal.parse_dataset_files("chamadas-por-apis-dados-abertos", PORTAL_HTML)
    assert len(files) == 1
    assert files[0].title == "Consolidado Agosto 2025"
    assert files[0].date_range == "Dados de 26/07/2025 a 29/08/2025"
    assert files[0].file_type == "CSV"
    assert files[0].download_url.endswith("id=51b0a27a-a295-43c4-b275-53c010e6ced1")


def test_openfinance_rejects_unsafe_ids() -> None:
    client = TestClient(app)

    org = client.get("/openfinance/directory/organisations/not-a-uuid/application-jwks")
    assert org.status_code == 400

    download = client.get("/openfinance/portal/download/not-a-uuid")
    assert download.status_code == 400


@respx.mock
def test_openfinance_participants_endpoint_filters() -> None:
    clear_cache()
    respx.get(PARTICIPANTS_URL).mock(return_value=httpx.Response(200, json=PARTICIPANTS))

    client = TestClient(app)
    r = client.get(
        "/openfinance/participants",
        params={"role": "DADOS", "api_family": "channels", "limit": 10},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["organisation_id"] == "org-1"
    assert body[0]["roles"] == ["DADOS"]


@respx.mock
def test_openfinance_public_resource_routes() -> None:
    clear_cache()
    respx.get(ROLES_URL).mock(return_value=httpx.Response(200, json=[{"Role": "DADOS"}]))
    respx.get(API_RESOURCES_URL).mock(
        return_value=httpx.Response(200, json=[{"ApiFamilyType": "channels"}])
    )
    respx.get(WELL_KNOWN_URL).mock(return_value=httpx.Response(200, json={"issuer": "issuer"}))
    respx.get(KEYSTORE_URL).mock(return_value=httpx.Response(200, json={"keys": []}))

    client = TestClient(app)
    assert client.get("/openfinance/directory/roles").json() == [{"Role": "DADOS"}]
    assert client.get("/openfinance/directory/api-resources").json() == [
        {"ApiFamilyType": "channels"}
    ]
    assert client.get("/openfinance/directory/well-known").json() == {"issuer": "issuer"}
    assert client.get("/openfinance/directory/keystore").json() == {"keys": []}


@respx.mock
def test_openfinance_portal_files_and_download_routes() -> None:
    clear_cache()
    respx.get(
        "https://dados.openfinancebrasil.org.br/conjuntos-de-dados/chamadas-por-apis-dados-abertos"
    ).mock(return_value=httpx.Response(200, text=PORTAL_HTML))
    respx.get(
        "https://dados.openfinancebrasil.org.br/api/download?id=51b0a27a-a295-43c4-b275-53c010e6ced1"
    ).mock(return_value=httpx.Response(200, content=b"col\n1\n"))

    client = TestClient(app)
    files = client.get("/openfinance/portal/datasets/chamadas-por-apis-dados-abertos/files")
    assert files.status_code == 200
    assert files.json()[0]["download_id"] == "51b0a27a-a295-43c4-b275-53c010e6ced1"

    download = client.get("/openfinance/portal/download/51b0a27a-a295-43c4-b275-53c010e6ced1")
    assert download.status_code == 200
    assert download.text == "col\n1\n"
