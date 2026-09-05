import { expect, test } from "@playwright/test";

const password = process.env.STRAYHUB_PHASE_E_PASSWORD ?? "";

test.skip(
  process.env.STRAYHUB_PHASE_E_GATEWAY !== "1" || !password,
  "Requires the controlled shared-demo-production gateway and synthetic fixture DB",
);
test.use({ trace: "off" });

async function login(page: import("@playwright/test").Page, username: string) {
  await page.goto("/login");
  await page.getByLabel("帳號").fill(username);
  await page.getByLabel("密碼").fill(password);
  const response = page.waitForResponse(
    (candidate) => new URL(candidate.url()).pathname === "/v1/auth/login",
  );
  await page.getByRole("button", { name: "登入" }).click();
  return response;
}

test("SHELTER_ADMIN keeps Core access while governance and PII stay closed", async ({
  page,
}) => {
  expect((await login(page, "local-shelter-admin-a")).status()).toBe(200);
  await expect(page).toHaveURL(/\/$/);
  for (const path of ["/animals", "/reports", "/ai-review", "/care-calendar"]) {
    expect((await page.goto(path))?.status(), path).toBe(200);
  }
  for (const path of [
    "/platform-admins",
    "/settings",
    "/volunteers",
    "/pii-reveal",
  ]) {
    expect((await page.goto(path))?.status(), path).toBe(404);
  }
  await expect(
    page.getByRole("link", { name: /平台|設定|志工治理/ }),
  ).toHaveCount(0);
});

for (const username of ["local-platform-admin", "local-volunteer-a"]) {
  test(`${username} is denied by server-side remote login policy`, async ({
    page,
  }) => {
    const response = await login(page, username);
    expect([401, 403]).toContain(response.status());
    await expect(page).toHaveURL(/\/login$/);
  });
}
