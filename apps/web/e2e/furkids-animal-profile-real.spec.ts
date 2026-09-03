import { expect, test } from "@playwright/test";

// Opt-in local Demo verification: saves existing profile values, never new fixtures.
test.skip(
  process.env.FURKIDS_PROFILE_REAL !== "1",
  "Requires migrated and seeded local FurKids DB/MinIO",
);
test.use({ trace: "off" });
const animals = [
  ["獒黃妹", "MTF-20140531-001", "female", "獒犬", "10歲以上"],
  ["獒一搓", "MTF-20241213-001", "male", "藏獒", "5歲以上"],
  ["獒瓦蛤", "MTF-20240515-001", "female", "藏獒", "5歲以上"],
  ["獒凱西", "MTF-20200605-001", "female", "混種獒犬", "7歲以上"],
  ["柴福福", "SBA-20170922-001", "male", "混種柴犬", "5歲以上"],
];

for (const viewport of [
  { width: 360, height: 800 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
]) {
  test(`real FurKids list/detail/edit/confirmation ${viewport.width}`, async ({
    page,
    context,
  }) => {
    test.setTimeout(90_000);
    await page.setViewportSize(viewport);
    await page.goto("/login");
    await page.getByLabel("帳號", { exact: true }).fill("demo-furkids-admin");
    await page.getByLabel("密碼", { exact: true }).fill("local-only-password");
    await page.getByRole("button", { name: "登入", exact: true }).click();
    await page
      .getByLabel("目前收容所", { exact: true })
      .selectOption({ label: "毛小孩幸福聯盟協會（FURKIDS-ASIA）" });
    await page
      .getByRole("button", { name: "進入管理工作台", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "管理工作台總覽", exact: true }),
    ).toBeVisible();
    await page.goto("/animals");
    for (const [name, number] of animals) {
      await expect(page.getByRole("link", { name, exact: true })).toBeVisible();
      await expect(
        page.getByRole("cell", { name: number, exact: true }),
      ).toBeVisible();
      await expect
        .poll(() =>
          page
            .getByRole("img", { name: `${name} 的照片`, exact: true })
            .evaluate(
              (e: HTMLImageElement) => e.complete && e.naturalWidth > 0,
            ),
        )
        .toBe(true);
    }
    const links = await Promise.all(
      animals.map(async ([name]) =>
        page.getByRole("link", { name, exact: true }).getAttribute("href"),
      ),
    );
    const qrDeepLinks: string[] = [];
    for (const [index, [name, number, sex, breed, age]] of animals.entries()) {
      const qrResponse = page.waitForResponse(
        (response) =>
          response.url().includes("/v1/management/qr-codes?animal_id=") &&
          response.request().method() === "GET",
      );
      await page.goto(links[index]!);
      await expect(
        page.getByRole("heading", { name, exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("region", {
          name: `${name}的照護回報 QR Code 標籤`,
          exact: true,
        }),
      ).toBeVisible();
      const qrData = await (await qrResponse).json();
      qrDeepLinks.push(
        qrData.items.find(
          (qr: { status: string; revoked: boolean }) =>
            qr.status === "active" && !qr.revoked,
        ).deep_link,
      );
      await expect(page.getByText(age, { exact: true })).toBeVisible();
      await expect(page.getByLabel("收容編號", { exact: true })).toContainText(
        number,
      );
      await expect
        .poll(() =>
          page
            .getByRole("img", { name: `${name} 的照片`, exact: true })
            .evaluate(
              (e: HTMLImageElement) => e.complete && e.naturalWidth > 0,
            ),
        )
        .toBe(true);
      await page
        .getByRole("button", { name: "編輯基本資料", exact: true })
        .click();
      await expect(page.getByLabel("性別", { exact: true })).toHaveValue(sex);
      await expect(page.getByLabel("品種", { exact: true })).toHaveValue(breed);
      await expect(page.getByLabel("出生日期", { exact: true })).toHaveValue(
        "",
      );
      await page
        .getByRole("button", { name: "儲存基本資料", exact: true })
        .click();
      await expect(
        page.getByText("基本資料已儲存", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "編輯基本資料", exact: true }),
      ).toBeFocused();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    const volunteer = await context.newPage();
    await volunteer.setViewportSize(viewport);
    await volunteer.goto("/login");
    await volunteer
      .getByLabel("帳號", { exact: true })
      .fill("demo-furkids-volunteer");
    await volunteer
      .getByLabel("密碼", { exact: true })
      .fill("local-only-password");
    await volunteer.getByRole("button", { name: "登入", exact: true }).click();
    await expect(volunteer).toHaveURL(/\/$/);
    for (const [index, [name, number, _sex, breed, age]] of animals.entries()) {
      // Use the existing server-generated locator without exposing it to logs.
      await volunteer.goto(qrDeepLinks[index]);
      const card = volunteer.locator(".animal-confirmation-card");
      await expect(card).toContainText(name);
      await expect(card).toContainText(number);
      await expect(card).toContainText(breed);
      await expect(card).toContainText(age);
      await expect
        .poll(() =>
          card
            .getByRole("img", { name: `${name} 的照片`, exact: true })
            .evaluate(
              (e: HTMLImageElement) => e.complete && e.naturalWidth > 0,
            ),
        )
        .toBe(true);
      expect(
        await volunteer.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
  });
}
