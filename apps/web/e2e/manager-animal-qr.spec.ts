import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

const deepLink =
  "/animal-confirmation?organization_id=org-a&qr_token=opaque-playwright-locator-123456";

const adminOrganizations = [
  {
    id: "org-a",
    code: "ORG-A",
    name: "浪浪森友會 A",
    role: "SHELTER_ADMIN",
    status: "active",
    timezone: "Asia/Taipei",
    timezone_version: 1,
  },
];

async function mockAnimalQrManagement(page: Page, initiallyReady = false) {
  let current = initiallyReady
    ? {
        id: "qr-a",
        organization_id: "org-a",
        animal_id: "animal-a",
        status: "active",
        revoked: false,
        token: null,
        deep_link: deepLink,
      }
    : null;
  let createCount = 0;

  await mockManagementApi(page, {
    organizations: adminOrganizations,
    platformRole: null,
  });
  await page.route("**/v1/management/qr-codes**", async (route, request) => {
    if (request.method() === "POST" && request.url().endsWith("/qr-codes")) {
      createCount += 1;
      current = {
        id: "qr-a",
        organization_id: "org-a",
        animal_id: "animal-a",
        status: "active",
        revoked: false,
        token: null,
        deep_link: deepLink,
      };
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(current),
      });
      return;
    }
    if (request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: current ? [current] : [] }),
      });
      return;
    }
    await route.fallback();
  });

  return { getCreateCount: () => createCount };
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
    window.print = () => {
      document.documentElement.dataset.printInvoked = "true";
    };
  });
});

test("manager generates, previews, and invokes print from the animal detail", async ({
  page,
}) => {
  const state = await mockAnimalQrManagement(page);
  await page.goto("/animals/animal-a");

  await expect(
    page.getByRole("heading", { name: "照護 QR Code" }),
  ).toBeVisible();
  await expect(page.getByText("尚未建立照護 QR Code")).toBeVisible();
  expect(state.getCreateCount()).toBe(0);

  await page.getByRole("button", { name: "建立照護 QR" }).click();
  await expect(page.locator(".animal-care-qr-image svg")).toBeVisible();
  await expect(page.locator(".animal-qr-print-label")).toContainText("小森");
  await expect(page.locator(".animal-qr-print-label")).toContainText("A-001");
  await expect(page.locator(".animal-qr-print-label")).toContainText(
    "浪浪森友會 A",
  );
  await expect(page.getByText("opaque-playwright-locator-123456")).toHaveCount(
    0,
  );
  expect(state.getCreateCount()).toBe(1);

  await page.getByRole("button", { name: "重新列印" }).click();
  await expect(page.locator("html")).toHaveAttribute(
    "data-print-invoked",
    "true",
  );
});

for (const viewport of [
  { width: 360, height: 800 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
]) {
  test(`16-character shelter number remains intact at ${viewport.width}px`, async ({
    page,
  }) => {
    const shelterNumber = "TW2026A000000001";
    await page.setViewportSize(viewport);
    await mockManagementApi(page, {
      animalDetails: {
        "animal-a": {
          id: "animal-a",
          organization_id: "org-a",
          name: "小森",
          shelter_number: shelterNumber,
          status: "active",
          photo_key: null,
          area_name: "一區",
          area_type: "room",
        },
      },
    });
    await page.goto("/animals/animal-a");

    const number = page.locator(".animal-profile-number strong");
    await expect(number).toHaveText(shelterNumber);
    await expect(number).toHaveCSS("white-space", "nowrap");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
  });
}

for (const viewport of [
  { width: 360, height: 800 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
]) {
  test(`ready QR label is responsive and accessible at ${viewport.width}x${viewport.height}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    const state = await mockAnimalQrManagement(page, true);
    await page.goto("/animals/animal-a");

    await expect(page.locator(".animal-care-qr-image svg")).toBeVisible();
    expect(state.getCreateCount()).toBe(0);
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
  });
}

test("A4 print media contains only an unclipped 50mm QR label", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockAnimalQrManagement(page, true);
  await page.goto("/animals/animal-a");
  await expect(page.locator(".animal-care-qr-image svg")).toBeVisible();

  await page.emulateMedia({ media: "print" });
  await expect(page.locator(".app-sidebar")).toHaveCSS("display", "none");
  await expect(page.locator(".animal-care-qr-actions")).toHaveCSS(
    "display",
    "none",
  );
  const qrBox = await page.locator(".animal-care-qr-image svg").boundingBox();
  expect(qrBox?.width).toBeGreaterThanOrEqual(185);
  expect(qrBox?.width).toBeLessThanOrEqual(195);
  const labelBox = await page.locator(".animal-qr-print-label").boundingBox();
  expect(labelBox?.x).toBeGreaterThanOrEqual(0);
  expect((labelBox?.x ?? 0) + (labelBox?.width ?? 0)).toBeLessThan(794);
  expect((labelBox?.y ?? 0) + (labelBox?.height ?? 0)).toBeLessThan(1123);

  await page.pdf({
    path: testInfo.outputPath("animal-care-qr-a4.pdf"),
    format: "A4",
    printBackground: true,
  });
});
