import { expect, test } from "@playwright/test";
import {
  confirmModal,
  gotoOverview,
  openActivities,
  setE2EState,
  waitForSseConnect,
} from "./helpers";

test.describe("Binggo smoke @smoke", () => {
  test.describe.configure({ mode: "serial" });

  test("1 opens console with hashed assets", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (err) => pageErrors.push(String(err)));

    const assetOk = page.waitForResponse(
      (res) => res.url().includes("/assets/") && res.status() === 200,
      { timeout: 20_000 },
    );
    const sseOk = waitForSseConnect(page);
    await page.goto("/");
    await assetOk;
    await sseOk;
    await expect(page).toHaveTitle(/Binggo/);
    await expect(page.getByRole("heading", { name: "概览" })).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("#stats-grid")).toBeVisible();
    expect(pageErrors, `uncaught page errors: ${pageErrors.join("; ")}`).toEqual([]);
  });

  test("2 activities list and filter", async ({ page }) => {
    await gotoOverview(page);
    await openActivities(page);
    await expect(page.locator("#activities-body tr").first()).toBeVisible({ timeout: 15_000 });
    await page.locator("[data-filter-status='未参加']").click();
    await expect(page.locator("#pagination")).toBeVisible();
    await expect(page.locator("#activities-body")).toBeVisible();
  });

  test("2b removes an activity from the list and automatic targets", async ({ page, request }) => {
    await gotoOverview(page);
    await openActivities(page);

    const row = page.locator("#activities-body tr[data-dynamic-id]").first();
    await expect(row).toBeVisible({ timeout: 15_000 });
    const dynamicId = await row.getAttribute("data-dynamic-id");
    expect(dynamicId).toBeTruthy();

    let deleteRequests = 0;
    page.on("request", (req) => {
      if (req.method() === "DELETE" && req.url().includes("/api/activities/")) {
        deleteRequests += 1;
      }
    });

    await row.locator("[data-activity-delete]").click();
    await expect(page.locator("#app-confirm-modal")).toBeVisible();
    await expect(page.locator("#app-confirm-yes")).toHaveClass(/btn-danger/);
    await page.locator("#app-confirm-cancel").click();
    await expect(page.locator("#app-confirm-modal")).toBeHidden();
    expect(deleteRequests).toBe(0);

    await row.locator("[data-activity-delete]").click();
    const deleted = page.waitForResponse(
      (res) =>
        res.request().method() === "DELETE" &&
        res.url().endsWith(`/api/activities/${dynamicId}`),
      { timeout: 10_000 },
    );
    await page.locator("#app-confirm-yes").click();
    expect((await deleted).status()).toBe(200);

    await expect(page.locator(`[data-dynamic-id="${dynamicId}"]`)).toHaveCount(0);
    await expect(page.locator(".toast-message").filter({ hasText: "活动已删除" })).toBeVisible();

    const activities = await request.get("/api/activities");
    expect(activities.ok()).toBeTruthy();
    const payload = await activities.json();
    expect(
      payload.items.some((item: { dynamic_id?: string }) => item.dynamic_id === dynamicId),
    ).toBe(false);
    expect(
      payload.triple_targets.items.some(
        (item: { dynamic_id?: string }) => item.dynamic_id === dynamicId,
      ),
    ).toBe(false);
  });

  test("3a AUTH gate blocks refresh_status before request", async ({ page, request }) => {
    // 前端 requireSetup 在未登录时直接 toast，不发 POST（与现网行为一致）
    await setE2EState(request, { account: "logged_out", llm: "not_ready" });
    await gotoOverview(page);

    let sawJobsPost = false;
    page.on("request", (req) => {
      if (req.method() === "POST" && req.url().includes("/api/jobs") && !req.url().includes("cancel")) {
        sawJobsPost = true;
      }
    });

    await page.locator('[data-action="refresh_status"]').first().click();
    await expect(page.locator(".toast-message").filter({ hasText: /登录/ })).toBeVisible({
      timeout: 8_000,
    });
    expect(sawJobsPost).toBe(false);
  });

  test("3b LLM_NOT_READY on refresh_all via API", async ({ page, request }) => {
    // settings 文件为 ready，前端放行；后端 hook llm=not_ready → 契约码
    await setE2EState(request, { account: "logged_in", llm: "not_ready" });
    await gotoOverview(page);

    const jobRespPromise = page.waitForResponse(
      (res) =>
        res.url().includes("/api/jobs") &&
        res.request().method() === "POST" &&
        !res.url().includes("cancel"),
      { timeout: 20_000 },
    );
    await page.locator('[data-action="refresh_all"]').first().click();
    await confirmModal(page);
    const jobResp = await jobRespPromise;
    expect(jobResp.status()).toBe(401);
    const body = await jobResp.json();
    expect(body.error?.code).toBe("LLM_NOT_READY");
    await expect(
      page.locator(".toast-message").filter({ hasText: /请先测试 LLM 连接/ }),
    ).toBeVisible({ timeout: 8_000 });
  });

  test("4 job start success for refresh_status", async ({ page, request }) => {
    await setE2EState(request, { account: "logged_in", llm: "ready" });
    await gotoOverview(page);

    const jobRespPromise = page.waitForResponse(
      (res) =>
        res.url().includes("/api/jobs") &&
        res.request().method() === "POST" &&
        !res.url().includes("cancel"),
      { timeout: 15_000 },
    );
    await page.locator('[data-action="refresh_status"]').first().click();
    const jobResp = await jobRespPromise;
    expect(jobResp.status()).toBe(200);
    const body = await jobResp.json();
    expect(body.ok).toBeTruthy();
    expect(body.job?.id).toBeTruthy();

    await expect
      .poll(
        async () => {
          const current = await request.get("/api/jobs/current");
          expect(current.ok()).toBeTruthy();
          const job = await current.json();
          return job.state;
        },
        { timeout: 15_000, intervals: [100, 200, 500] },
      )
      .toBe("success");
  });

  test("5 settings panels load", async ({ page, request }) => {
    await setE2EState(request, { account: "logged_in", llm: "ready" });
    await gotoOverview(page);
    await expect(page.locator("#llm-settings-panel")).toBeVisible();
    await expect(page.locator("#participate-text-input")).toBeVisible();
    await expect(page.locator("#save-llm-settings")).toBeVisible();
    await expect(page.locator("#save-participate-text")).toBeVisible();

    const settingsResp = page.waitForResponse(
      (res) => res.url().includes("/api/settings/llm") && res.request().method() === "GET",
      { timeout: 10_000 },
    );
    await page.locator("#refresh-llm-settings").click();
    const resp = await settingsResp;
    expect(resp.status()).toBe(200);
  });
});
