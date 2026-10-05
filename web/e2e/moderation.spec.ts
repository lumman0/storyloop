import { expect, test } from "@playwright/test";
import { commonApi } from "./support";

test("upload v2 keeps pending v1 withdrawable and unlocks v2 submission afterwards", async ({ page }) => {
  let latest = { id: "story", title: "测试剧本", summary: "", mode: "freeform", status: "draft",
    version_id: "version1", package_version: "1", review_status: "pending", public_state: null };
  let history = [{ scenario_id: "story", submission_id: "submission1", version_id: "version1",
    package_version: "1", status: "pending", reason: "" }];
  const mutations: string[] = [];
  await page.route("**/v1/**", async (route) => {
    if (await commonApi(route)) return;
    const path = new URL(route.request().url()).pathname;
    if (path === "/v1/my-scenarios") return route.fulfill({ json: { scenarios: [latest] } });
    if (path === "/v1/my-submissions") return route.fulfill({ json: { submissions: history } });
    if (path === "/v1/my-scenarios/story/versions") {
      latest = { ...latest, version_id: "version2", package_version: "2", review_status: "" };
      mutations.push("upload2");
      return route.fulfill({ json: latest });
    }
    if (path === "/v1/my-submissions/submission1" && route.request().method() === "DELETE") {
      history[0] = { ...history[0], status: "withdrawn" };
      mutations.push("withdraw1");
      return route.fulfill({ json: history[0] });
    }
    if (path === "/v1/my-scenarios/story/submit") {
      const submission = { ...history[0], submission_id: "submission2", version_id: "version2", package_version: "2", status: "pending" };
      history = [...history, submission];
      mutations.push("submit2");
      return route.fulfill({ json: submission });
    }
    return route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });
  await page.goto("/my-scenarios");
  await expect(page.getByRole("button", { name: "撤回该版本申请" })).toBeVisible();
  await page.locator("#version-story").setInputFiles({ name: "revision.zip", mimeType: "application/zip", buffer: Buffer.from("test fixture") });
  await expect(page.getByText("最新上传版本 2", { exact: false })).toBeVisible();
  await expect(page.getByText("版本 1（version1）正在审核", { exact: false })).toBeVisible();
  const submit = page.getByRole("button", { name: "提交最新版本审核" });
  await expect(submit).toBeDisabled();
  await page.getByRole("button", { name: "撤回该版本申请" }).click();
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(page.getByText("版本 2（version2）正在审核", { exact: false })).toBeVisible();
  expect(mutations).toEqual(["upload2", "withdraw1", "submit2"]);
});

test("slow A detail cannot overwrite B or submit B's opinion against A", async ({ page }) => {
  let releaseA!: () => void;
  const blockedA = new Promise<void>((resolve) => { releaseA = resolve; });
  let requestedA = false;
  const decisions: { id: string; body: unknown }[] = [];
  const detail = (id: string) => ({ submission_id: id, scenario_id: id, version_id: id,
    title: `剧本${id}`, summary: "", package_version: "1", package_hash: id, status: "pending",
    author_name: "作者", submitted_at: 1, mode: "freeform", manifest: {}, worldbook: {} });
  await page.route("**/v1/**", async (route) => {
    if (await commonApi(route)) return;
    const path = new URL(route.request().url()).pathname;
    if (path === "/v1/manage/submissions") return route.fulfill({ json: { submissions: [detail("A"), detail("B")] } });
    if (path.endsWith("/decision")) {
      decisions.push({ id: path.split("/").at(-2)!, body: route.request().postDataJSON() });
      return route.fulfill({ json: { status: "approved" } });
    }
    if (path === "/v1/manage/submissions/A") {
      requestedA = true;
      await blockedA;
      return route.fulfill({ json: detail("A") });
    }
    if (path === "/v1/manage/submissions/B") return route.fulfill({ json: detail("B") });
    return route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });
  await page.goto("/manage");
  await page.getByRole("button", { name: /剧本A/ }).click();
  await expect.poll(() => requestedA).toBe(true);
  await page.getByRole("button", { name: /剧本B/ }).click();
  const reason = page.getByLabel("审核意见；驳回或管理员审核自己的剧本时必填");
  await expect(reason).toBeEnabled();
  await reason.fill("B版本可以通过");
  const late = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/submissions/A"));
  releaseA();
  await late;
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByRole("heading", { name: "剧本B" })).toBeVisible();
  await expect(reason).toHaveValue("B版本可以通过");
  const refreshedQueue = page.waitForResponse((response) => new URL(response.url()).pathname === "/v1/manage/submissions");
  await page.getByRole("button", { name: "通过并公开" }).click();
  await expect.poll(() => decisions).toEqual([{ id: "B", body: { decision: "approved", reason: "B版本可以通过" } }]);
  await refreshedQueue;
  await expect(page.getByText("该版本已通过审核并进入公共目录。", { exact: true })).toBeVisible();
});
