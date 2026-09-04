import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";

const originalApiBaseUrl = process.env.API_BASE_URL;

describe("/v1 proxy conditional responses", () => {
  beforeEach(() => {
    process.env.API_BASE_URL = "http://127.0.0.1:8001";
  });

  afterEach(() => {
    if (originalApiBaseUrl === undefined) delete process.env.API_BASE_URL;
    else process.env.API_BASE_URL = originalApiBaseUrl;
    vi.unstubAllGlobals();
  });

  it("preserves a 304 response and its cache validators", async () => {
    const upstreamFetch = vi.fn().mockResolvedValue(
      new Response(null, {
        status: 304,
        headers: {
          "Cache-Control": "private, max-age=300, must-revalidate",
          ETag: '"checksum"',
          Vary: "Authorization, X-Session-ID",
        },
      }),
    );
    vi.stubGlobal("fetch", upstreamFetch);
    const request = new NextRequest(
      "http://localhost/v1/management/animals/animal-a/photo?v=checksum",
      { headers: { "If-None-Match": '"checksum"' } },
    );

    const response = await GET(request, {
      params: Promise.resolve({
        path: ["management", "animals", "animal-a", "photo"],
      }),
    });

    expect(response.status).toBe(304);
    expect(await response.text()).toBe("");
    expect(response.headers.get("cache-control")).toBe(
      "private, max-age=300, must-revalidate",
    );
    expect(response.headers.get("etag")).toBe('"checksum"');
    expect(upstreamFetch).toHaveBeenCalledWith(
      expect.objectContaining({ search: "?v=checksum" }),
      expect.objectContaining({
        cache: "no-store",
        headers: expect.any(Headers),
      }),
    );
    const forwardedHeaders = upstreamFetch.mock.calls[0][1].headers as Headers;
    expect(forwardedHeaders.get("if-none-match")).toBe('"checksum"');
  });

  it("continues to reject upstream redirects", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(null, {
          status: 302,
          headers: { Location: "https://example.test" },
        }),
      ),
    );
    const request = new NextRequest("http://localhost/v1/example");

    const response = await GET(request, {
      params: Promise.resolve({ path: ["example"] }),
    });

    expect(response.status).toBe(502);
  });
});
