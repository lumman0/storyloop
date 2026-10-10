import { expect, test, type Page, type Route } from "@playwright/test";
import { commonApi, view } from "./support";

async function playerApi(page: Page, initial: typeof view & Record<string, unknown>, turn: (route: Route) => Promise<void>) {
  await page.route("**/v1/**", async (route) => {
    if (await commonApi(route)) return;
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/turns/stream")) return turn(route);
    if (path === "/v1/saves") return route.fulfill({ json: { saves: [{ ...initial, title: "测试故事", available: true }] } });
    if (path.endsWith("/resume")) return route.fulfill({ json: initial });
    if (path.endsWith("/history")) return route.fulfill({ json: { game_id: "game", intro: initial, turns: [] } });
    if (path.endsWith("/cast")) return route.fulfill({ json: { cast: [] } });
    if (path.endsWith("/player-card")) return route.fulfill({ json: { name: "", fields: [] } });
    if (path.endsWith("/settings")) return route.fulfill({ json: { temperature: 1, context_window_tokens: 65536,
      default_temperature: 1, default_context_window_tokens: 65536, max_context_window_tokens: 65536 } });
    return route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });
}

test("old oversized choice unlocks editing and submits a shorter note with a fresh ID", async ({ page }) => {
  const oldNote = "字".repeat(10000);
  await page.addInitScript((text) => sessionStorage.setItem("storyloop.pending.game",
    JSON.stringify({ id: "old-request", text })), `/choose dockhand ${oldNote}`);
  const calls: { request_id: string; text: string }[] = [];
  await playerApi(page, { ...view, interaction: { id: "choice", kind: "message", prompt: "给谁留言？",
    options: [{ id: "dockhand", label: "码头工", enabled: true, requires_text: true }] } }, async (route) => {
    const input = route.request().postDataJSON();
    calls.push(input);
    const event = calls.length === 1
      ? { type: "error", message: "留言过长", code: "INVALID_TURN_INPUT", retryable: false,
        commit_state: "not_started", request_id: input.request_id }
      : { type: "complete", view: { ...view, state_version: 1, body: "留言已送达。", turn_id: input.request_id } };
    await route.fulfill({ contentType: "text/event-stream", body: `data: ${JSON.stringify(event)}\n\n` });
  });
  await page.goto("/play/game");
  await page.getByRole("button", { name: "重试这条行动" }).click();
  const note = page.getByRole("textbox", { name: "写下你的留言" });
  await expect(note).toBeEnabled();
  await expect(note).toHaveValue(oldNote);
  await expect(page.getByRole("button", { name: "确认选择" })).toBeDisabled();
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("storyloop.pending.game"))).toBeNull();
  await note.fill("你好");
  await page.getByRole("button", { name: "确认选择" }).click();
  await expect(page.getByText("留言已送达。", { exact: true })).toBeVisible();
  expect(calls).toHaveLength(2);
  expect(calls[0].request_id).toBe("old-request");
  expect(calls[1].request_id).not.toBe("old-request");
  expect(calls[1].text).toBe("/choose dockhand 你好");
});

test("disconnected stream retains original input and request ID across refresh", async ({ page }) => {
  const calls: { request_id: string; text: string }[] = [];
  await playerApi(page, view, async (route) => {
    calls.push(route.request().postDataJSON());
    await route.fulfill({ contentType: "text/event-stream", body: 'data: {"type":"stage","stage":"thinking"}\n\n' });
  });
  await page.goto("/play/game");
  await page.getByLabel("写下你的行动或想说的话").fill("我走向码头");
  await page.getByLabel("写下你的行动或想说的话").press("Enter");
  await expect(page.getByRole("button", { name: "重试这条行动" })).toBeVisible();
  await expect(page.getByLabel("写下你的行动或想说的话")).toHaveCount(0);
  await page.reload();
  await page.getByRole("button", { name: "重试这条行动" }).click();
  await expect.poll(() => calls.length).toBe(2);
  expect(calls[1]).toEqual(calls[0]);
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem("storyloop.pending.game")!))).toEqual({
    id: calls[0].request_id, text: "我走向码头",
  });
});

test("manual recovery remains blocked after refresh with the original request preserved", async ({ page }) => {
  let requestId = "";
  await playerApi(page, view, async (route) => {
    requestId = route.request().postDataJSON().request_id;
    await route.fulfill({ contentType: "text/event-stream", body: `data: ${JSON.stringify({
      type: "error", message: "这条行动需要人工恢复，请联系管理员。",
      code: "TURN_RECOVERY_REQUIRED", commit_state: "unknown", retryable: false, request_id: requestId,
    })}\n\n` });
  });
  await page.goto("/play/game");
  await page.getByLabel("写下你的行动或想说的话").fill("我走向码头");
  await page.getByLabel("写下你的行动或想说的话").press("Enter");
  await expect(page.getByText("这条行动需要人工恢复，请联系管理员。", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("这条行动需要人工恢复，请联系管理员。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "重试这条行动" })).toHaveCount(0);
  await expect(page.getByLabel("写下你的行动或想说的话")).toHaveCount(0);
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem("storyloop.pending.game")!))).toEqual({
    id: requestId, text: "我走向码头", retryable: false, error: "这条行动需要人工恢复，请联系管理员。",
  });
});

for (const outcome of ["unknown event", "malformed complete", "invalid JSON", "malformed HTTP failure"]) {
  test(`${outcome} retains input and request ID across refresh and retry`, async ({ page }) => {
    const calls: { request_id: string; text: string }[] = [];
    await playerApi(page, view, async (route) => {
      const input = route.request().postDataJSON();
      calls.push(input);
      if (outcome === "malformed HTTP failure") {
        return route.fulfill({ status: 400, json: { detail: "Incomplete failure metadata",
          commit_state: "not_started", request_id: input.request_id } });
      }
      const data = outcome === "unknown event" ? JSON.stringify({ type: "future", commit_state: "not_started", request_id: input.request_id })
        : outcome === "malformed complete" ? JSON.stringify({ type: "complete", view: { body: "Malformed content" } }) : "{invalid";
      await route.fulfill({ contentType: "text/event-stream", body: `data: ${data}\n\n` });
    });
    await page.goto("/play/game");
    await page.getByLabel("写下你的行动或想说的话").fill("我走向码头");
    await page.getByLabel("写下你的行动或想说的话").press("Enter");
    await expect(page.getByRole("button", { name: "重试这条行动" })).toBeVisible();
    await expect(page.getByLabel("写下你的行动或想说的话")).toHaveCount(0);
    await expect(page.getByText("Malformed content", { exact: true })).toHaveCount(0);
    await page.reload();
    await page.getByRole("button", { name: "重试这条行动" }).click();
    await expect.poll(() => calls.length).toBe(2);
    expect(calls[1]).toEqual(calls[0]);
    expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem("storyloop.pending.game")!))).toEqual({
      id: calls[0].request_id, text: "我走向码头",
    });
  });
}
