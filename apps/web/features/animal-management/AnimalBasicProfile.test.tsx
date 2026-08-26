// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { AnimalBasicProfile } from "./AnimalBasicProfile";
import type { ManagementAnimal } from "../../lib/animal-profile";

vi.mock("../../lib/auth", () => ({
  authFetch: (...args: unknown[]) =>
    fetch(...(args as Parameters<typeof fetch>)),
}));
(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;
const animal: ManagementAnimal = {
  id: "animal-a",
  organization_id: "org-a",
  name: "獒一搓",
  shelter_number: "MTF-20241213-001",
  status: "active",
  photo_key: null,
  area_id: null,
  area_name: null,
  area_type: null,
  sex: "male",
  birth_date_estimated: false,
  breed: "藏獒",
  intake_date: null,
  birth_date: null,
  age_description: null,
  behavior_notes: null,
  care_guidance: null,
  photo_url: null,
  area_path: null,
};
const container = document.createElement("div");
let root: ReturnType<typeof createRoot>;
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

it("edits through the profile endpoint, preserves audit-only status flow and restores focus", async () => {
  document.body.appendChild(container);
  root = createRoot(container);
  const saved = vi.fn();
  const fetchMock = vi.fn(async () => ({
    ok: true,
    json: async () => ({ animal }),
  }));
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
  await act(async () =>
    root.render(<AnimalBasicProfile animal={animal} onSaved={saved} />),
  );
  const edit = container.querySelector("button")!;
  await act(async () => edit.click());
  expect(container.querySelector('label[for="profile-sex"]')?.textContent).toBe(
    "性別",
  );
  expect(container.querySelectorAll('input[type="date"]')).toHaveLength(2);
  expect(container.querySelectorAll("textarea")).toHaveLength(2);
  await act(async () =>
    container
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
  expect(fetchMock).toHaveBeenCalledWith(
    "/v1/management/animals/animal-a/profile",
    expect.objectContaining({ method: "PATCH" }),
  );
  const payload = JSON.parse(
    (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1]
      .body as string,
  );
  expect(payload.sex).toBe("male");
  expect(payload).not.toHaveProperty("status");
  expect(payload).not.toHaveProperty("organization_id");
  expect(saved).toHaveBeenCalledWith(animal);
  expect(document.activeElement).toBe(edit);
  expect(container.textContent).toContain("基本資料已儲存");
});

it("focuses an accessible validation error and does not send invalid dates", async () => {
  document.body.appendChild(container);
  root = createRoot(container);
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    setTimeout(() => callback(0), 0);
    return 1;
  });
  await act(async () =>
    root.render(<AnimalBasicProfile animal={animal} onSaved={vi.fn()} />),
  );
  await act(async () => container.querySelector("button")!.click());
  (container.querySelector('[name="birth_date"]') as HTMLInputElement).value =
    "2021-01-01";
  (container.querySelector('[name="intake_date"]') as HTMLInputElement).value =
    "2020-01-01";
  await act(async () =>
    container
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
  await act(async () => new Promise((resolve) => setTimeout(resolve, 5)));
  expect(fetchMock).not.toHaveBeenCalled();
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    "出生日期不得晚於入園日期",
  );
  expect(document.activeElement).toBe(
    container.querySelector('[role="alert"]'),
  );
});
