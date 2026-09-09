import {
  expect,
  test,
  type Browser,
  type Page,
  type Request,
} from "@playwright/test";
import { mockLoginApi } from "./fixtures";

const username = "phase-a-synthetic-user";
const password = "phase-a-synthetic-password";

async function fillLogin(page: Page) {
  await page.getByLabel("帳號").fill(username);
  await page.getByLabel("密碼").fill(password);
}

async function expectJsonCredentialPost(request: Request) {
  const url = new URL(request.url());
  expect(request.method()).toBe("POST");
  expect(url.pathname).toBe("/v1/auth/login");
  expect(url.search).toBe("");
  await expect(request.headerValue("content-type")).resolves.toContain(
    "application/json",
  );
  expect(request.postDataJSON()).toEqual({ username, password });
}

test("click login sends credentials only in the JSON API body", async ({
  page,
}) => {
  const loginRequests: Request[] = [];
  await mockLoginApi(page, {
    onLoginRequest: (request) => loginRequests.push(request),
  });
  await page.goto("/login");
  await fillLogin(page);
  await page.getByRole("button", { name: "登入" }).click();

  await expect(page).toHaveURL(/\/$/);
  expect(loginRequests).toHaveLength(1);
  await expectJsonCredentialPost(loginRequests[0]);
  expect(page.url()).not.toContain("username=");
  expect(page.url()).not.toContain("password=");
});

test("Enter login keeps a failed credential out of URL, UI error and console", async ({
  page,
}) => {
  const loginRequests: Request[] = [];
  const consoleMessages: string[] = [];
  page.on("console", (message) => consoleMessages.push(message.text()));
  await mockLoginApi(page, {
    loginStatus: 401,
    onLoginRequest: (request) => loginRequests.push(request),
  });
  await page.goto("/login");
  await fillLogin(page);
  await page.getByLabel("密碼").press("Enter");

  const error = page.locator("#login-error");
  await expect(error).toContainText("登入失敗");
  await expect(error).not.toContainText(username);
  await expect(error).not.toContainText(password);
  expect(loginRequests).toHaveLength(1);
  await expectJsonCredentialPost(loginRequests[0]);
  expect(page.url()).not.toContain(username);
  expect(page.url()).not.toContain(password);
  expect(consoleMessages.join("\n")).not.toContain(username);
  expect(consoleMessages.join("\n")).not.toContain(password);
});

test("network failure remains a generic login error without URL credentials", async ({
  page,
}) => {
  await mockLoginApi(page, { loginStatus: "network" });
  await page.goto("/login");
  await fillLogin(page);
  await page.getByRole("button", { name: "登入" }).click();

  await expect(page.locator("#login-error")).toContainText("登入失敗");
  expect(page.url()).not.toContain(username);
  expect(page.url()).not.toContain(password);
});

test("legacy credential query is removed with replacement and never reflected", async ({
  page,
}) => {
  const sentinels = ["legacy-user-sentinel", "legacy-password-sentinel"];
  const consoleMessages: string[] = [];
  const loginRequests: Request[] = [];
  page.on("console", (message) => consoleMessages.push(message.text()));
  await mockLoginApi(page, {
    onLoginRequest: (request) => loginRequests.push(request),
  });
  await page.goto("/login");
  await page.evaluate((values) => {
    window.location.assign(
      `/login?view=login&username=${encodeURIComponent(values[0])}&password=${encodeURIComponent(values[1])}&password=duplicate`,
    );
  }, sentinels);

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel("帳號")).toHaveValue("");
  await expect(page.getByLabel("密碼")).toHaveValue("");
  const text = await page.locator("body").innerText();
  for (const sentinel of sentinels) {
    expect(text).not.toContain(sentinel);
    expect(consoleMessages.join("\n")).not.toContain(sentinel);
  }
  expect(loginRequests).toHaveLength(0);

  await page.goBack();
  await expect(page).toHaveURL(/\/login$/);
  expect(page.url()).not.toContain("username=");
  expect(page.url()).not.toContain("password=");
});

test("encoded and case-variant Class A keys canonicalize without becoming form state", async ({
  page,
}) => {
  await page.goto(
    "/login?PASS%57ORD=value&TEMPORARY-PASSWORD=value&access_token=value&refresh_token=value&id_token=value&authorization=value",
  );

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel("帳號")).toHaveValue("");
  await expect(page.getByLabel("密碼")).toHaveValue("");
});

test("ordinary query state is not treated as login input", async ({ page }) => {
  await page.goto("/login?view=login&page=2");

  await expect(page).toHaveURL(/\/login\?view=login&page=2$/);
  await expect(page.getByLabel("帳號")).toHaveValue("");
  await expect(page.getByLabel("密碼")).toHaveValue("");
});

test("login responses prevent caching and referrer propagation", async ({
  page,
}) => {
  const response = await page.goto("/login");

  expect(response?.headers()["cache-control"]).toContain("no-store");
  expect(response?.headers()["referrer-policy"]).toBe("no-referrer");
});

async function assertFailClosedBeforeHydration(
  browser: Browser,
  javaScriptEnabled: boolean,
) {
  const context = await browser.newContext({ javaScriptEnabled });
  if (javaScriptEnabled) {
    await context.route(/\/\_next\/.*\.js(?:\?.*)?$/, (route) => route.abort());
  }
  const page = await context.newPage();
  const requests: Request[] = [];
  page.on("request", (request) => requests.push(request));
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("button", { name: "登入" })).toBeDisabled();
  await fillLogin(page);
  await page.getByLabel("密碼").press("Enter");

  expect(page.url()).not.toContain("username=");
  expect(page.url()).not.toContain("password=");
  expect(
    requests.some(
      (request) => new URL(request.url()).pathname === "/v1/auth/login",
    ),
  ).toBe(false);
  await context.close();
}

test("JavaScript disabled cannot create a credential GET", async ({
  browser,
}) => {
  await assertFailClosedBeforeHydration(browser, false);
});

test("blocked Next scripts keep pre-hydration Enter fail-closed", async ({
  browser,
}) => {
  await assertFailClosedBeforeHydration(browser, true);
});
