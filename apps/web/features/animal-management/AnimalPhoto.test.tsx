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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  fetchPhoto.mockReset();
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
