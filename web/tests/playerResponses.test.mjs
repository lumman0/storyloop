import assert from "node:assert/strict";
import test from "node:test";
import { ApiError, readTurnStream, responseError } from "../src/lib/playerResponses.ts";
import { savePendingTurn, readPendingTurn, discardUnstartedTurn } from "../src/lib/pendingTurn.ts";

test("malformed HTTP failure metadata cannot clear a pending action", () => {
  const error = responseError(400, { detail: "Shorten input", commit_state: "not_started", request_id: "original" });
  assert.equal(error.failure, undefined);
  assert.equal(error.message, "Shorten input");
  assert.equal(responseError(400, { detail: { private: "payload" } }).message.includes("payload"), false);
});

test("bad JSON, unknown events and malformed complete/error retain the original pending request", async () => {
  const values = new Map();
  const storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
  savePendingTurn("game", { id: "original", text: "Original action" }, storage);
  for (const data of ["{private", JSON.stringify({ type: "future" }), JSON.stringify({ type: "complete", view: { body: "private" } }),
    JSON.stringify({ type: "error", commit_state: "not_started", request_id: "original" })]) {
    const events = [];
    await assert.rejects(readTurnStream(new Response(`data: ${data}\n\n`), (event) => events.push(event)), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.failure, undefined);
      assert.equal(error.message.includes("private"), false);
      assert.equal(discardUnstartedTurn("game", "original", error.failure, storage), false);
      return true;
    });
    assert.deepEqual(events, []);
    assert.deepEqual(readPendingTurn("game", storage), { id: "original", text: "Original action" });
  }
});

test("only valid terminal failures supply execution evidence", async () => {
  const failure = { type: "error", code: "INVALID_TURN_INPUT", message: "Shorten input", retryable: false,
    commit_state: "not_started", request_id: "original" };
  await assert.rejects(readTurnStream(new Response(`data: ${JSON.stringify(failure)}\n\n`), () => {}),
    (error) => error instanceof ApiError && error.failure?.request_id === "original" && error.failure?.commit_state === "not_started");
});
