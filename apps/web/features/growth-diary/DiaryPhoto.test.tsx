// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchGrowthDiaryPhoto } from "./api";
import { DiaryPhoto } from "./DiaryPhoto";

vi.mock("./api", async (importOriginal) => {
  const original = await importOriginal<typeof import("./api")>();
  return { ...original, fetchGrowthDiaryPhoto: vi.fn() };
});

const fetchPhoto = vi.mocked(fetchGrowthDiaryPhoto);
const createObjectURL = vi.fn(() => "blob:growth-diary-photo");
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

describe("DiaryPhoto", () => {
  it("uses an authenticated Blob URL and revokes it on unmount", async () => {
    fetchPhoto.mockResolvedValue(new Blob(["webp"], { type: "image/webp" }));
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () =>
      root.render(<DiaryPhoto entryId="entry-a" alt="米糕的日記照片" />),
    );

    expect(fetchPhoto).toHaveBeenCalledWith("entry-a", expect.any(AbortSignal));
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(container.querySelector("img")?.getAttribute("src")).toBe(
      "blob:growth-diary-photo",
    );
    await act(async () => root.unmount());
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:growth-diary-photo");
  });

  it("aborts and ignores a stale photo when the entry or tenant subtree changes", async () => {
    const photoA = deferred<Blob>();
    const photoB = deferred<Blob>();
    fetchPhoto.mockImplementation((entryId) =>
      entryId === "entry-a" ? photoA.promise : photoB.promise,
    );
    createObjectURL.mockReturnValue("blob:b");
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () =>
      root.render(<DiaryPhoto entryId="entry-a" alt="A" />),
    );
    const signalA = fetchPhoto.mock.calls[0][1];
    await act(async () =>
      root.render(<DiaryPhoto entryId="entry-b" alt="B" />),
    );
    expect(signalA?.aborted).toBe(true);

    await act(async () => photoA.resolve(new Blob(["a"])));
    expect(container.querySelector("img")?.getAttribute("src")).not.toBe(
      "blob:a",
    );
    expect(createObjectURL).not.toHaveBeenCalled();
    await act(async () => photoB.resolve(new Blob(["b"])));
    expect(container.querySelector("img")?.getAttribute("src")).toBe("blob:b");
    await act(async () => root.unmount());
  });

  it("shows a local fallback after image decode failure", async () => {
    fetchPhoto.mockResolvedValue(new Blob(["broken"]));
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () =>
      root.render(<DiaryPhoto entryId="entry-a" alt="米糕的日記照片" />),
    );

    await act(async () =>
      container.querySelector("img")?.dispatchEvent(new Event("error")),
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("照片暫時無法顯示");
    await act(async () => root.unmount());
  });
});
