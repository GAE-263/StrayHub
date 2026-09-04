// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { authFetch } from "../../lib/auth";
import { AnimalPhoto } from "./AnimalPhoto";

vi.mock("../../lib/auth", () => ({ authFetch: vi.fn() }));

const fetchPhoto = vi.mocked(authFetch);
const createObjectURL = vi.fn(() => "blob:animal-photo");
const revokeObjectURL = vi.fn();
type ObserverHarness = {
  callback: IntersectionObserverCallback;
  options?: IntersectionObserverInit;
  instance: IntersectionObserver;
};
let observers: ObserverHarness[] = [];

function installIntersectionObserver() {
  const MockIntersectionObserver = vi.fn(
    (
      callback: IntersectionObserverCallback,
      options?: IntersectionObserverInit,
    ) => {
      const instance = {
        disconnect: vi.fn(),
        observe: vi.fn(),
        root: null,
        rootMargin: options?.rootMargin ?? "0px",
        takeRecords: vi.fn(() => []),
        thresholds: [0],
        unobserve: vi.fn(),
      } as unknown as IntersectionObserver;
      observers.push({ callback, options, instance });
      return instance;
    },
  );
  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
}

function enterViewport(observer: ObserverHarness) {
  observer.callback(
    [{ isIntersecting: true } as IntersectionObserverEntry],
    observer.instance,
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  vi.unstubAllGlobals();
  fetchPhoto.mockReset();
  observers = [];
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: createObjectURL,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: revokeObjectURL,
  });
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe("AnimalPhoto", () => {
  it("does not fetch outside the viewport and uses a 200px preload margin", async () => {
    installIntersectionObserver();
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () =>
      root.render(<AnimalPhoto photoUrl="/v1/a/photo" alt="A" />),
    );

    expect(fetchPhoto).not.toHaveBeenCalled();
    expect(observers).toHaveLength(1);
    expect(observers[0].options).toEqual({ rootMargin: "200px" });
    expect(observers[0].instance.observe).toHaveBeenCalledOnce();
    await act(async () => root.unmount());
  });

  it("fetches once when repeated observer callbacks enter the viewport", async () => {
    installIntersectionObserver();
    fetchPhoto.mockResolvedValue(
      new Response(new Blob(["jpeg"], { type: "image/jpeg" }), { status: 200 }),
    );
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () =>
      root.render(<AnimalPhoto photoUrl="/v1/a/photo" alt="A" />),
    );

    await act(async () => {
      enterViewport(observers[0]);
      enterViewport(observers[0]);
    });

    expect(fetchPhoto).toHaveBeenCalledOnce();
    expect(container.querySelector("img")?.getAttribute("src")).toBe(
      "blob:animal-photo",
    );
    await act(async () => root.unmount());
  });

  it("loads through authFetch and revokes the Blob URL on unmount", async () => {
    fetchPhoto.mockResolvedValue(
      new Response(new Blob(["jpeg"], { type: "image/jpeg" }), { status: 200 }),
    );
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () =>
      root.render(
        <AnimalPhoto
          photoUrl="/v1/management/animals/a/photo"
          alt="小森的照片"
        />,
      ),
    );

    expect(fetchPhoto).toHaveBeenCalledWith(
      "/v1/management/animals/a/photo",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(container.querySelector("img")?.getAttribute("src")).toBe(
      "blob:animal-photo",
    );
    await act(async () => root.unmount());
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:animal-photo");
  });

  it("aborts and never publishes a stale response after the URL changes", async () => {
    const first = deferred<Response>();
    fetchPhoto
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(new Response(new Blob(["b"]), { status: 200 }));
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () =>
      root.render(<AnimalPhoto photoUrl="/v1/a/photo" alt="A" />),
    );
    const firstSignal = fetchPhoto.mock.calls[0][1]?.signal;
    await act(async () =>
      root.render(<AnimalPhoto photoUrl="/v1/b/photo" alt="B" />),
    );
    expect(firstSignal?.aborted).toBe(true);
    await act(async () => first.resolve(new Response(new Blob(["a"]))));

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(container.querySelector("img")?.getAttribute("alt")).toBe("B");
    await act(async () => root.unmount());
  });

  it("re-observes a changed URL and aborts the previous visible request", async () => {
    installIntersectionObserver();
    const first = deferred<Response>();
    fetchPhoto
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(new Response(new Blob(["b"]), { status: 200 }));
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () =>
      root.render(<AnimalPhoto photoUrl="/v1/a/photo" alt="A" />),
    );
    await act(async () => enterViewport(observers[0]));
    const firstSignal = fetchPhoto.mock.calls[0][1]?.signal;

    await act(async () =>
      root.render(<AnimalPhoto photoUrl="/v1/b/photo" alt="B" />),
    );

    expect(firstSignal?.aborted).toBe(true);
    expect(fetchPhoto).toHaveBeenCalledOnce();
    expect(observers).toHaveLength(2);
    await act(async () => enterViewport(observers[1]));
    expect(fetchPhoto).toHaveBeenCalledTimes(2);
    await act(async () => first.resolve(new Response(new Blob(["a"]))));
    expect(container.querySelector("img")?.getAttribute("alt")).toBe("B");
    await act(async () => root.unmount());
  });

  it("aborts an in-flight request on unmount", async () => {
    const pending = deferred<Response>();
    fetchPhoto.mockReturnValue(pending.promise);
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () =>
      root.render(<AnimalPhoto photoUrl="/v1/a/photo" alt="A" />),
    );
    const signal = fetchPhoto.mock.calls[0][1]?.signal;

    await act(async () => root.unmount());

    expect(signal?.aborted).toBe(true);
  });

  it("does not fetch when no photo URL is provided", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () => root.render(<AnimalPhoto photoUrl={null} alt="A" />));

    expect(fetchPhoto).not.toHaveBeenCalled();
    expect(container.innerHTML).toBe("");
    await act(async () => root.unmount());
  });

  it("shows a local fallback for an HTTP failure", async () => {
    fetchPhoto.mockResolvedValue(new Response(null, { status: 404 }));
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () =>
      root.render(<AnimalPhoto photoUrl="/v1/a/photo" alt="A" />),
    );

    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("照片暫時無法顯示");
    await act(async () => root.unmount());
  });

  it("revokes an undecodable Blob and shows the local fallback", async () => {
    fetchPhoto.mockResolvedValue(
      new Response(new Blob(["broken"]), { status: 200 }),
    );
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () =>
      root.render(<AnimalPhoto photoUrl="/v1/a/photo" alt="A" />),
    );
    await act(async () =>
      container.querySelector("img")?.dispatchEvent(new Event("error")),
    );

    expect(revokeObjectURL).toHaveBeenCalledWith("blob:animal-photo");
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("照片暫時無法顯示");
    await act(async () => root.unmount());
  });
});
