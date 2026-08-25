export type AnimalQrPayload = {
  token: string;
  candidateOrganizationId: string | null;
};

const TOKEN_KEYS = ["qr_token", "token"] as const;
const ORGANIZATION_KEYS = ["organization_id", "organization"] as const;

function fromParams(params: URLSearchParams): AnimalQrPayload | null {
  const token = TOKEN_KEYS.map((key) => params.get(key)?.trim()).find(Boolean);
  if (!token) return null;
  const candidateOrganizationId =
    ORGANIZATION_KEYS.map((key) => params.get(key)?.trim()).find(Boolean) ??
    null;
  return { token, candidateOrganizationId };
}

export function parseAnimalQrPayload(raw: string): AnimalQrPayload | null {
  const value = raw.trim();
  if (!value) return null;
  try {
    const url = new URL(value, "https://strayhub.invalid");
    const parsed = fromParams(url.searchParams);
    if (parsed) return parsed;
  } catch {
    // A scanner may return the opaque token directly.
  }
  if (/^[A-Za-z0-9_-]{20,512}$/.test(value)) {
    return { token: value, candidateOrganizationId: null };
  }
  return null;
}

export function animalQrPayloadFromLocation(
  location: Pick<Location, "search">,
): AnimalQrPayload | null {
  return fromParams(new URLSearchParams(location.search));
}
