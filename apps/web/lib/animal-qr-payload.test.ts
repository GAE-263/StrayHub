import { describe, expect, it } from "vitest";
import {
  animalQrPayloadFromLocation,
  parseAnimalQrPayload,
} from "./animal-qr-payload";

describe("animal QR payload parsing", () => {
  it("extracts only locator token and candidate organization from canonical deep links", () => {
    expect(
      parseAnimalQrPayload(
        "https://liff.line.me/example/animal-confirmation?organization_id=org-b&qr_token=opaque-token-123456789",
      ),
    ).toEqual({
      token: "opaque-token-123456789",
      candidateOrganizationId: "org-b",
    });
  });

  it("supports an opaque scanner result without inventing animal identity", () => {
    expect(parseAnimalQrPayload("opaque-token-123456789")).toEqual({
      token: "opaque-token-123456789",
      candidateOrganizationId: null,
    });
  });

  it("rejects arbitrary text and ignores untrusted animal fields", () => {
    expect(parseAnimalQrPayload("not a QR payload")).toBeNull();
    expect(
      parseAnimalQrPayload(
        "/animal-confirmation?qr_token=opaque-token-123456789&animal_id=animal-fake&animal_name=Fake",
      ),
    ).toEqual({
      token: "opaque-token-123456789",
      candidateOrganizationId: null,
    });
  });

  it("reads direct-entry query parameters without persisting them", () => {
    expect(
      animalQrPayloadFromLocation({
        search: "?organization_id=org-a&qr_token=opaque-token-123456789",
      } as Location),
    ).toEqual({
      token: "opaque-token-123456789",
      candidateOrganizationId: "org-a",
    });
  });
});
