// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { authFetch } from "./auth";
import { apiFetch } from "./api";
import {
  activateOrganizationRequests,
  clearOrganizationRequests,
  pauseOrganizationRequests,
} from "./organization-request-scope";

afterEach(() => {
  clearOrganizationRequests();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

it("organization and generation both participate in request identity", () => {
  const a = activateOrganizationRequests("org-a");
  expect(activateOrganizationRequests("org-a")).toBe(a);
  pauseOrganizationRequests();
  const b = activateOrganizationRequests("org-b");
  const nextA = activateOrganizationRequests("org-a");
  expect(new Set([a.key, b.key, nextA.key]).size).toBe(3);
  expect(a.signal.aborted).toBe(true);
});

it("aborts pending requests and rejects a late response even when fetch ignores abort", async () => {
  activateOrganizationRequests("org-a");
  let resolve!: (response: Response) => void;
  let signal!: AbortSignal;
  vi.stubGlobal(
    "fetch",
    vi.fn((_input, init) => {
      signal = init.signal;
      return new Promise<Response>((done) => {
        resolve = done;
      });
    }),
  );
  const pending = authFetch("/v1/animals/animal-a/timeline");
  pauseOrganizationRequests();
  expect(signal.aborted).toBe(true);
  activateOrganizationRequests("org-b");
  resolve(new Response(JSON.stringify({ days: ["old"] })));
  await expect(pending).rejects.toMatchObject({ name: "AbortError" });
});

it("blocks new animal requests while switching but permits context reconciliation", async () => {
  activateOrganizationRequests("org-a");
  pauseOrganizationRequests();
  const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
  vi.stubGlobal("fetch", fetchMock);
  await expect(
    authFetch("/v1/management/animals/animal-a"),
  ).rejects.toMatchObject({ name: "AbortError" });
  expect(fetchMock).not.toHaveBeenCalled();
  await authFetch("/v1/auth/active-shelter-context");
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it("guards an old JSON body that finishes after switching away and back", async () => {
  activateOrganizationRequests("org-a");
  let resolve!: (value: unknown) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      status: 200,
      json: () =>
        new Promise((done) => {
          resolve = done;
        }),
    }),
  );
  const response = await authFetch("/v1/management/reports/report-a");
  const json = response.json();
  pauseOrganizationRequests();
  activateOrganizationRequests("org-b");
  activateOrganizationRequests("org-a");
  resolve({ report: "stale" });
  await expect(json).rejects.toMatchObject({ name: "AbortError" });
});

it.each(["text", "blob", "arrayBuffer", "formData"] as const)(
  "guards a late %s body and prevents its consumer side effect",
  async (reader) => {
    activateOrganizationRequests("org-a");
    let resolve!: (value: unknown) => void;
    const response = {
      ok: true,
      status: 200,
      [reader]: () =>
        new Promise((done) => {
          resolve = done;
        }),
    } as unknown as Response;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    const guarded = await authFetch("/v1/management/animals/animal-a/export");
    let consumed = false;
    const body = (guarded[reader] as () => Promise<unknown>)().then((value) => {
      consumed = true;
      return value;
    });
    pauseOrganizationRequests();
    activateOrganizationRequests("org-b");
    resolve("late org-a body");

    await expect(body).rejects.toMatchObject({ name: "AbortError" });
    expect(consumed).toBe(false);
  },
);

it("keeps caller abort behavior for medical history filters", async () => {
  activateOrganizationRequests("org-a");
  const controller = new AbortController();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}")));
  const response = await authFetch("/v1/management/animals/a/medical-records", {
    signal: controller.signal,
  });
  controller.abort();
  await expect(response.json()).rejects.toMatchObject({ name: "AbortError" });
});

it("never retries an A request under B after an in-flight token refresh", async () => {
  activateOrganizationRequests("org-a");
  sessionStorage.setItem("access_token", "access-a");
  sessionStorage.setItem("refresh_token", "refresh-a");
  let resolve!: (response: Response) => void;
  const fetchMock = vi.fn((input) =>
    input === "/v1/auth/refresh"
      ? new Promise<Response>((done) => {
          resolve = done;
        })
      : Promise.resolve(new Response("{}", { status: 401 })),
  );
  vi.stubGlobal("fetch", fetchMock);
  const pending = apiFetch("/v1/management/animals/animal-a/medical-records");
  await vi.waitFor(() => expect(resolve).toBeDefined());
  pauseOrganizationRequests();
  activateOrganizationRequests("org-b");
  resolve(
    new Response(
      JSON.stringify({ access_token: "refreshed", session_id: "session-a" }),
    ),
  );
  await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(sessionStorage.getItem("access_token")).toBe("access-a");
});
