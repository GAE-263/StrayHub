import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { mockVolunteerApi } from "./fixtures";

const animalA = {
  id: "animal-a",
  name: "小森",
  shelter_number: "A-001",
  photo_url: null,
  cage: "犬舍 A3",
  area: "北區",
  can_report: true,
  organization_id: "org-a",
};

const animalB = {
  ...animalA,
  id: "animal-b",
  name: "小白",
  shelter_number: "B-002",
  organization_id: "org-b",
};

async function mockQrFlow(
  page: Page,
  options: { crossShelter?: boolean; authorizeCrossShelter?: boolean } = {},
) {
  await mockVolunteerApi(page);
  let activeOrganizationId = "org-a";
  const requests: Array<{ path: string; body: unknown }> = [];

  await page.route("**/v1/**", async (route, request) => {
    const url = new URL(request.url());
    const body = request.postDataJSON?.() ?? null;
    requests.push({ path: url.pathname, body });

    if (url.pathname === "/v1/auth/active-shelter-context") {
      if (request.method() === "PUT") {
        const requested = (body as { organization_id?: string } | null)
          ?.organization_id;
        if (requested === "org-b" && options.authorizeCrossShelter !== false) {
          activeOrganizationId = "org-b";
        } else if (requested !== "org-a") {
          await route.fulfill({
            status: 403,
            contentType: "application/json",
            body: "{}",
          });
          return;
        }
      }
      const isB = activeOrganizationId === "org-b";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          organization_id: activeOrganizationId,
          organization_name: isB ? "北投收容所" : "浪浪森友會 A",
          session_id: "test-session",
        }),
      });
      return;
    }
    if (url.pathname === "/v1/qr-tokens/candidate-organization") {
      const authorized = options.authorizeCrossShelter !== false;
      await route.fulfill({
        status: authorized ? 200 : 403,
        contentType: "application/json",
        body: JSON.stringify(
          authorized
            ? { organization_id: "org-b", organization_name: "北投收容所" }
            : { code: "authorization_no_longer_valid", message: "無法存取" },
        ),
      });
      return;
    }
    if (url.pathname === "/v1/qr-tokens/resolve") {
      const animal =
        options.crossShelter && activeOrganizationId === "org-b"
          ? animalB
          : animalA;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(animal),
      });
      return;
    }
    if (url.pathname === "/v1/animals/search") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [animalA], page: 1, page_size: 100 }),
      });
      return;
    }
    if (/\/v1\/animals\/[^/]+\/confirm$/.test(url.pathname)) {
      const animal = activeOrganizationId === "org-b" ? animalB : animalA;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...animal,
          confirmation_token: "short-lived-confirmation",
        }),
      });
      return;
    }
    if (url.pathname === "/v1/care-report-handoffs") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "pending",
          expires_at: "2026-08-25T12:15:00Z",
        }),
      });
      return;
    }
    await route.fallback();
  });

  return requests;
}

test("same-shelter QR deep link confirms animal and creates a handoff", async ({
  page,
}) => {
  const requests = await mockQrFlow(page);
  await page.goto(
    "/animal-confirmation?organization_id=org-a&qr_token=playwright-direct-token-123456",
  );

  await expect(
    page.getByRole("heading", { name: "確認照護動物" }),
  ).toBeVisible();
  await expect(page.getByText("小森")).toBeVisible();
  await expect(page).not.toHaveURL(/qr_token/);
  await page.getByRole("button", { name: "確認並開始回報" }).click();
  await expect(page.getByRole("heading", { name: "動物已確認" })).toBeVisible();
  await expect(page.getByText("再點一次「照護回報」")).toBeVisible();

  const handoff = requests.find(
    (item) => item.path === "/v1/care-report-handoffs",
  );
  expect(handoff?.body).toEqual({
    animal_id: "animal-a",
    confirmation_token: "short-lived-confirmation",
    source: "qr_deeplink",
  });
  expect(requests.some((item) => item.path === "/v1/care-report-drafts")).toBe(
    false,
  );
});

test("exact shelter-number fallback uses the same confirmation and handoff path", async ({
  page,
}) => {
  const requests = await mockQrFlow(page);
  await page.goto("/animal-confirmation");
  await page.getByRole("button", { name: "輸入完整收容編號" }).click();
  await page.getByRole("textbox", { name: "完整收容編號" }).fill("A-001");
  await page.getByRole("button", { name: "確認收容編號" }).click();
  await expect(
    page.getByRole("heading", { name: "確認照護動物" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "確認並開始回報" }).click();
  await expect(page.getByRole("heading", { name: "動物已確認" })).toBeVisible();
  expect(
    (
      requests.find((item) => item.path === "/v1/care-report-handoffs")
        ?.body as { source: string }
    ).source,
  ).toBe("shelter_number");
});

test("authorized cross-shelter QR requires an explicit switch before identity", async ({
  page,
}) => {
  await mockQrFlow(page, { crossShelter: true });
  await page.goto(
    "/animal-confirmation?organization_id=org-b&qr_token=playwright-cross-token-123456",
  );

  const dialog = page.getByRole("dialog", { name: "切換收容所" });
  await expect(dialog).toBeVisible();
  await expect(page.getByText("小白")).toHaveCount(0);
  await dialog.getByRole("button", { name: "切換並繼續" }).click();
  await expect(
    page.getByRole("heading", { name: "確認照護動物" }),
  ).toBeVisible();
  await expect(page.getByText("小白")).toBeVisible();
  await expect(
    page.getByText("收容所：北投收容所", { exact: true }),
  ).toBeVisible();
});

test("unauthorized cross-shelter QR and scanner-unavailable UI leak no identity", async ({
  page,
}) => {
  await mockQrFlow(page, { crossShelter: true, authorizeCrossShelter: false });
  await page.goto(
    "/animal-confirmation?organization_id=org-b&qr_token=playwright-denied-token-123456",
  );

  await expect(page.locator("p[role='alert']")).toContainText(
    "目前無法使用此收容所進行照護回報",
  );
  await expect(page.getByText("小白")).toHaveCount(0);
  await expect(page.getByText("此裝置目前無法直接掃描 QR Code")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "輸入完整收容編號" }),
  ).toBeEnabled();
});

for (const viewport of [
  { width: 360, height: 800 },
  { width: 1440, height: 900 },
]) {
  test(`scanner-first page is responsive and accessible at ${viewport.width}x${viewport.height}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    await mockQrFlow(page);
    await page.goto("/animal-confirmation");
    await expect(
      page.getByRole("button", { name: "掃描動物 QR Code" }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
    const results = await new AxeBuilder({ page }).analyze();
    expect(
      results.violations.filter((item) =>
        ["critical", "serious"].includes(item.impact ?? ""),
      ),
    ).toEqual([]);
    await page.screenshot({
      path: testInfo.outputPath(
        `scanner-first-${viewport.width}x${viewport.height}.png`,
      ),
      fullPage: true,
    });
  });
}
