import { expect, test } from "@playwright/test";

const password = process.env.STRAYHUB_PHASE_E_PASSWORD ?? "";

test.skip(
  process.env.STRAYHUB_PHASE_E_GATEWAY !== "1" || !password,
  "Requires the controlled shared-demo-production gateway and synthetic fixture DB",
);
test.use({ trace: "off" });

test("STAFF completes the Core Remote Management journey through the gateway", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const loginRequests: Array<{
    method: string;
    url: string;
    body: string | null;
  }> = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/v1/auth/login") {
      loginRequests.push({
        method: request.method(),
        url: request.url(),
        body: request.postData(),
      });
    }
  });

  await page.goto("/login");
  await page.getByLabel("帳號").fill("local-staff-a");
  await page.getByLabel("密碼").fill(password);
  await page.getByRole("button", { name: "登入" }).click();
  await expect(page).toHaveURL(/\/$/);
  expect(loginRequests).toHaveLength(1);
  expect(loginRequests[0]?.method).toBe("POST");
  expect(new URL(loginRequests[0]!.url).search).toBe("");
  expect(loginRequests[0]?.body).toContain('"username":"local-staff-a"');

  for (const path of [
    "/",
    "/animals",
    "/reports",
    "/ai-review",
    "/care-calendar",
  ]) {
    const response = await page.goto(path);
    expect(response?.status(), path).toBe(200);
    await expect(page.locator("body")).not.toContainText("Application error");
  }

  const apiEvidence = await page.evaluate(async () => {
    const token = sessionStorage.getItem("access_token");
    const headers = { Authorization: `Bearer ${token}` };
    const paths = [
      "/v1/auth/me",
      "/v1/management/dashboard",
      "/v1/management/animals",
      "/v1/management/reports",
      "/v1/management/ai-review",
      "/v1/management/care-calendar?date_from=2026-09-01&date_to=2026-09-30",
    ];
    return Promise.all(
      paths.map(async (path) => [
        path,
        (await fetch(path, { headers })).status,
      ]),
    );
  });
  expect(apiEvidence.every(([, status]) => status === 200)).toBe(true);

  const resourceEvidence = await page.evaluate(async () => {
    const token = sessionStorage.getItem("access_token");
    const headers = { Authorization: `Bearer ${token}` };
    const animalListResponse = await fetch("/v1/management/animals", {
      headers,
    });
    const animalList = (await animalListResponse.json()) as {
      items: Array<{ id: string; photo_url: string | null }>;
    };
    const animal = animalList.items.find((item) => item.photo_url);
    if (!animal?.photo_url)
      throw new Error("synthetic animal photo fixture is missing");
    const reportListResponse = await fetch("/v1/management/reports", {
      headers,
    });
    const reportList = (await reportListResponse.json()) as {
      items: Array<{ id: string }>;
    };
    const report = reportList.items[0];
    if (!report) throw new Error("synthetic report fixture is missing");
    const requests = [
      `/v1/management/animals/${animal.id}`,
      `/v1/animals/${animal.id}/timeline`,
      animal.photo_url,
      `/v1/management/reports/${report.id}`,
    ];
    return {
      animalId: animal.id,
      reportId: report.id,
      statuses: await Promise.all(
        requests.map(async (path) => [
          path,
          (await fetch(path, { headers })).status,
        ]),
      ),
    };
  });
  expect(resourceEvidence.statuses.every(([, status]) => status === 200)).toBe(
    true,
  );
  expect(
    (await page.goto(`/animals/${resourceEvidence.animalId}`))?.status(),
  ).toBe(200);
  expect(
    (
      await page.goto(`/animals/${resourceEvidence.animalId}/timeline`)
    )?.status(),
  ).toBe(200);
  expect(
    (await page.goto(`/reports/${resourceEvidence.reportId}`))?.status(),
  ).toBe(200);

  const refreshStatus = await page.evaluate(async () => {
    const refreshToken = sessionStorage.getItem("refresh_token");
    return (
      await fetch("/v1/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
    ).status;
  });
  expect(refreshStatus).toBe(200);
  await page.getByRole("button", { name: /登出/ }).click();
  await expect(page).toHaveURL(/\/login$/);
});
