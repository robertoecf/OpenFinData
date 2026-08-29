import { getJson, jsonResult } from "../lib/http";

const DATA = "https://data.directory.openbankingbrasil.org.br";

type Participant = Record<string, unknown>;

function asDicts(value: unknown): Participant[] {
  return Array.isArray(value) ? value.filter((item) => item && typeof item === "object") : [];
}

function summarise(item: Participant) {
  const servers = asDicts(item.AuthorisationServers);
  const roles = asDicts(item.OrgDomainRoleClaims)
    .map((claim) => String(claim.Role ?? ""))
    .filter(Boolean);
  let apiResources = 0;
  for (const server of servers) {
    apiResources += asDicts(server.ApiResources).length;
  }
  return {
    organisation_id: item.OrganisationId,
    organisation_name: item.OrganisationName ?? null,
    registered_name: item.RegisteredName ?? null,
    registration_number: item.RegistrationNumber ?? null,
    status: item.Status ?? null,
    roles: [...new Set(roles)].sort(),
    authorization_servers: servers.length,
    api_resources: apiResources,
  };
}

export async function openfinanceDirectory(args: {
  dataset?: "participants" | "endpoints" | "resources" | "roles";
  role?: string;
  status?: string;
  api_family?: string;
  q?: string;
  limit?: number;
}) {
  const dataset = args.dataset ?? "participants";
  const limit = args.limit ?? 100;
  if (dataset === "resources") {
    return jsonResult([
      { name: "participants", url: `${DATA}/participants` },
      { name: "roles", url: `${DATA}/roles` },
    ]);
  }
  if (dataset === "roles") {
    const raw = await getJson(`${DATA}/roles`, undefined, {
      maxBytes: 8_000_000,
      timeoutMs: 30_000,
    });
    return jsonResult(asDicts(raw).slice(0, limit));
  }
  const raw = asDicts(
    await getJson(`${DATA}/participants`, undefined, { maxBytes: 8_000_000, timeoutMs: 30_000 }),
  );
  const status = args.status ?? "Active";
  const q = args.q?.toLowerCase();
  const role = args.role?.toLowerCase();
  const family = args.api_family?.toLowerCase();
  const filtered = raw.filter((item) => {
    if (status && String(item.Status ?? "").toLowerCase() !== status.toLowerCase()) {
      return false;
    }
    if (q) {
      const hay = `${item.OrganisationName ?? ""} ${item.RegisteredName ?? ""} ${item.RegistrationNumber ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (role) {
      const roles = asDicts(item.OrgDomainRoleClaims).map((claim) =>
        String(claim.Role ?? "").toLowerCase(),
      );
      if (!roles.includes(role)) return false;
    }
    if (family) {
      let hit = false;
      for (const server of asDicts(item.AuthorisationServers)) {
        for (const resource of asDicts(server.ApiResources)) {
          if (String(resource.ApiFamilyType ?? "").toLowerCase().includes(family)) {
            hit = true;
          }
        }
      }
      if (!hit) return false;
    }
    return true;
  });
  if (dataset === "endpoints") {
    const endpoints: Record<string, unknown>[] = [];
    for (const org of filtered) {
      for (const server of asDicts(org.AuthorisationServers)) {
        for (const resource of asDicts(server.ApiResources)) {
          if (
            family &&
            !String(resource.ApiFamilyType ?? "").toLowerCase().includes(family)
          ) {
            continue;
          }
          for (const endpoint of asDicts(resource.ApiDiscoveryEndpoints)) {
            if (!endpoint.ApiEndpoint) continue;
            endpoints.push({
              organisation_id: org.OrganisationId,
              organisation_name: org.OrganisationName ?? null,
              api_family_type: resource.ApiFamilyType ?? null,
              api_endpoint: endpoint.ApiEndpoint,
            });
            if (endpoints.length >= limit) {
              return jsonResult(endpoints);
            }
          }
        }
      }
    }
    return jsonResult(endpoints);
  }
  return jsonResult(filtered.slice(0, limit).map(summarise));
}
