import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { GET, POST } from "./route";

const originalApiBaseUrl = process.env.API_BASE_URL;

it("preserves account transaction headers and independent HttpOnly cookies", async () => {
  process.env.API_BASE_URL = "http://127.0.0.1:8001";
  const headers = new Headers();
  headers.append(
    "Set-Cookie",
    "transaction-a=first; HttpOnly; Path=/; SameSite=Strict",
  );
  headers.append(
    "Set-Cookie",
    "transaction-b=second; HttpOnly; Path=/; SameSite=Strict",
  );
  const upstream = vi.fn().mockResolvedValue(new Response("{}", { headers }));
  vi.stubGlobal("fetch", upstream);
  try {
    const request = new NextRequest(
      "http://localhost:3001/v1/auth/google/exchange",
      {
        method: "POST",
        body: "{}",
        headers: {
          "Content-Length": "2",
          "Content-Type": "application/json",
          Origin: "http://localhost:3001",
          Cookie: "transaction-a=first",
          "X-CSRF-Token": "csrf",
          "X-StrayHub-Account": "1",
        },
      },
    );
    const response = await POST(request, {
      params: Promise.resolve({ path: ["auth", "google", "exchange"] }),
    });
    const forwarded = upstream.mock.calls[0][1].headers as Headers;
    expect(forwarded.get("origin")).toBe("http://localhost:3001");
    expect(forwarded.get("cookie")).toBe("transaction-a=first");
    expect(forwarded.get("x-csrf-token")).toBe("csrf");
    expect(response.headers.getSetCookie()).toHaveLength(2);
    expect(
      response.headers
        .getSetCookie()
        .every((cookie) => cookie.includes("HttpOnly")),
    ).toBe(true);
  } finally {
    vi.unstubAllGlobals();
    if (originalApiBaseUrl === undefined) delete process.env.API_BASE_URL;
    else process.env.API_BASE_URL = originalApiBaseUrl;
  }
});

describe("Next API proxy sensitive logging boundary", () => {
  beforeEach(() => {
    process.env.API_BASE_URL = "http://127.0.0.1:8001";
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    if (originalApiBaseUrl === undefined) delete process.env.API_BASE_URL;
    else process.env.API_BASE_URL = originalApiBaseUrl;
  });

  it("forwards ordinary and registered capability query without custom logging", async () => {
    const sentinel = "proxy-capability-sentinel";
    const stdout = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const stderr = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const upstream = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
      );
    const request = new NextRequest(
      `https://example.test/v1/public/animals/animal-a/photo?token=${sentinel}&page=2`,
    );

    const response = await GET(request, {
      params: Promise.resolve({
        path: ["public", "animals", "animal-a", "photo"],
      }),
    });

    expect(response.status).toBe(200);
    const target = upstream.mock.calls[0][0] as URL;
    expect(target.pathname).toBe("/v1/public/animals/animal-a/photo");
    expect(target.searchParams.get("token")).toBe(sentinel);
    expect(target.searchParams.get("page")).toBe("2");
    expect(stdout).not.toHaveBeenCalled();
    expect(stderr).not.toHaveBeenCalled();
  });

  it("returns a fixed error without printing raw target, body, or credential", async () => {
    const sentinel = "proxy-error-secret-sentinel";
    const stdout = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const stderr = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new Error(`password=${sentinel}`),
    );
    const request = new NextRequest(
      `https://example.test/v1/auth/login?password=${sentinel}`,
    );

    const response = await GET(request, {
      params: Promise.resolve({ path: ["auth", "login"] }),
    });
    const rendered = JSON.stringify(await response.json());

    expect(response.status).toBe(503);
    expect(rendered).not.toContain(sentinel);
    expect(stdout).not.toHaveBeenCalled();
    expect(stderr).not.toHaveBeenCalled();
  });
});

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
