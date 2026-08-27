import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockManagementApi, mockVolunteerApi } from "./fixtures";

const profiles = [
  ["獒黃妹", "MTF-20140531-001", "female", "獒犬", "2014-05-31", "10歲以上"],
  ["獒一搓", "MTF-20241213-001", "male", "藏獒", "2024-12-13", "5歲以上"],
  ["獒瓦蛤", "MTF-20240515-001", "female", "藏獒", "2024-05-15", "5歲以上"],
  ["獒凱西", "MTF-20200605-001", "female", "混種獒犬", "2020-06-05", "7歲以上"],
  ["柴福福", "SBA-20170922-001", "male", "混種柴犬", "2017-09-22", "5歲以上"],
].map(
  ([name, shelter_number, sex, breed, intake_date, age_description], i) => ({
    id: `profile-${i}`,
    organization_id: "org-a",
    name,
    shelter_number,
    sex,
    breed,
    intake_date,
    age_description,
    birth_date: null,
    birth_date_estimated: false,
    behavior_notes: "僅管理端可見的行為描述",
    care_guidance: "接近前請先出聲，依現場安排互動。",
    status: "active",
    area_id: "area-a",
    area_name: `M-0${i + 1}`,
    area_type: "cage",
    area_path: `大型犬區 / M-0${i + 1}`,
    photo_key: null,
    photo_url: null,
  }),
);

for (const viewport of [
  { width: 360, height: 800 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
]) {
  test(`動物 profile 清單、編輯與志工安全欄位 ${viewport.width}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.addInitScript(() => {
      sessionStorage.setItem("access_token", "test-access");
      sessionStorage.setItem("active_organization_id", "org-a");
    });
    await mockManagementApi(page, {
      animals: () => ({ items: profiles, total: 5, page: 1, page_size: 20 }),
      animalDetails: Object.fromEntries(
        profiles.map((animal) => [animal.id, animal]),
      ),
    });
    let saves = 0;
    await page.route("**/v1/management/animals/*/profile", async (route) => {
      const animal = profiles.find((item) =>
        route.request().url().includes(`/${item.id}/`),
      )!;
      const body = route.request().postDataJSON();
      expect(body).not.toHaveProperty("organization_id");
      expect(body).not.toHaveProperty("status");
      saves += 1;
      await route.fulfill({ json: { animal: { ...animal, ...body } } });
    });
    await page.goto("/animals");
    for (const animal of profiles) {
      await expect(
        page.getByRole("link", { name: animal.name, exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("cell", { name: animal.shelter_number, exact: true }),
      ).toBeVisible();
    }
    for (const animal of profiles) {
      await page.goto(`/animals/${animal.id}`);
      await expect(
        page.getByRole("heading", { name: animal.name, exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText(animal.age_description, { exact: true }),
      ).toBeVisible();
      await page
        .getByRole("button", { name: "編輯基本資料", exact: true })
        .click();
      await expect(page.getByLabel("性別", { exact: true })).toHaveValue(
        animal.sex,
      );
      await page.getByLabel("出生日期", { exact: true }).fill("2030-01-01");
      await page
        .getByRole("button", { name: "儲存基本資料", exact: true })
        .click();
      await expect(
        page.getByRole("alert").filter({ hasText: "出生日期不得晚於入園日期" }),
      ).toBeFocused();
      await page.getByLabel("出生日期", { exact: true }).fill("");
      await page.getByLabel("品種", { exact: true }).fill(animal.breed);
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
    expect(saves).toBe(5);
    await page
      .getByRole("button", { name: "編輯基本資料", exact: true })
      .click();
    expect(
      (
        await new AxeBuilder({ page })
          .include('form[aria-label="編輯動物基本資料"]')
          .analyze()
      ).violations,
    ).toEqual([]);

    await mockVolunteerApi(page);
    let current = profiles[0];
    await page.route("**/v1/qr-tokens/resolve", async (route) => {
      const {
        behavior_notes: _internal,
        intake_date: _intake,
        ...safe
      } = current;
      await route.fulfill({
        json: {
          ...safe,
          cage: safe.area_name,
          area: "大型犬區",
          can_report: true,
        },
      });
    });
    for (const animal of profiles) {
      current = animal;
      await page.goto(
        "/animal-confirmation?organization_id=org-a&qr_token=profile-test-opaque-token",
      );
      const card = page.locator(".animal-confirmation-card");
      await expect(card).toContainText(animal.name);
      await expect(card).toContainText(animal.shelter_number);
      await expect(card).toContainText(animal.breed);
      await expect(card).toContainText(animal.age_description);
      await expect(
        card.getByRole("heading", { name: "照護提醒" }),
      ).toBeVisible();
      await expect(card).not.toContainText(animal.behavior_notes);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    expect(
      (
        await new AxeBuilder({ page })
          .include(".animal-confirmation-card")
          .analyze()
      ).violations,
    ).toEqual([]);
  });
}
