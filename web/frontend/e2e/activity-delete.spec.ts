import { expect, test, type Page } from "@playwright/test";

import { confirmModal, gotoOverview, openActivities, setE2EState } from "./helpers";

async function gotoActivities(page: Page) {
  await gotoOverview(page);
  await openActivities(page);
}

test("delete activity, list it, and restore it", async ({ page, request }) => {
  await setE2EState(request, { account: "logged_in", llm: "ready" });
  await gotoActivities(page);

  const row = page.locator('tr.activity-row[data-dynamic-id="1111111111111111111"]');
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "删除活动" }).click();
  await expect(page.getByText("删除这个活动？")).toBeVisible();
  await confirmModal(page);

  await expect(page.locator('tr.activity-row[data-dynamic-id="1111111111111111111"]')).toHaveCount(0);
  await page.getByRole("button", { name: /已删除/ }).click();
  const deletedRow = page.locator('[data-deleted-dynamic-id="1111111111111111111"]');
  await expect(deletedRow).toBeVisible();
  await expect(page.locator("tr.activity-row")).toHaveCount(2);
  await page.waitForTimeout(700);
  await page.locator("#section-activities .activities-panel").evaluate((panel) => {
    panel.classList.remove("is-activities-entering");
  });
  await page.locator("tr.activity-row").evaluateAll((rows) => {
    rows.forEach((row) => row.classList.remove("is-row-entering"));
  });
  await page.screenshot({
    path: "../../output/playwright/activity-deleted-desktop.png",
    fullPage: true,
    animations: "disabled",
  });

  await deletedRow.getByRole("button", { name: "恢复" }).click();
  await expect(page.locator('tr.activity-row[data-dynamic-id="1111111111111111111"]')).toBeVisible();
});

test("deleted activity list stays usable on mobile", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setE2EState(request, { account: "logged_in", llm: "ready" });
  await gotoOverview(page);
  await page.locator("#sidebar-toggle").click();
  await openActivities(page);

  const card = page.locator('.activity-card[data-dynamic-id="1111111111111111111"]');
  await card.getByRole("button", { name: "删除活动" }).click();
  await confirmModal(page);
  await page.getByRole("button", { name: /已删除/ }).click();

  await expect(page.locator('[data-deleted-dynamic-id="1111111111111111111"]')).toBeVisible();
  await page.screenshot({
    path: "../../output/playwright/activity-deleted-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
});
