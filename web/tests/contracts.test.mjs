import assert from "node:assert/strict";
import test from "node:test";
import { parseView, parseHistory, parseTurnFailure, parseTurnStreamEvent, ContractError } from "../src/lib/contracts.ts";
import { discardUnstartedTurn, readPendingTurn, savePendingTurn } from "../src/lib/pendingTurn.ts";

const view = { game_id: "game", catalog_id: "story", mode: "freeform", presentation_mode: "interactive",
  opening: "", body: "", segments: [], suggestions: [], action_options: [], status_fields: [],
  interaction: null, tick: 0, state_version: 0, day: null, time_of_day: null, complete: false, turn_id: null };
const failure = { code: "INVALID_TURN_INPUT", message: "Shorten input", retryable: false,
  commit_state: "not_started", request_id: "original" };

test("production parsers validate nullable keys and preserve omitted keys without mutation", () => {
  const before = structuredClone(view);
  assert.equal(parseView(view), view);
  assert.deepEqual(view, before);
  assert.equal("billing" in view, false);
  assert.equal(parseHistory({ game_id: "game", intro: view, turns: [{ request_id: "original", input: null, response: view }] }).turns[0].input, null);
  assert.equal(parseTurnFailure(failure), failure);
  for (const event of [ { type: "stage", stage: "received" }, { type: "segment", segment: { kind: "time", text: "" } },
    { type: "preview", body: "", segments: [] }, { type: "complete", view }, { type: "error", ...failure } ]) {
    assert.equal(parseTurnStreamEvent(event), event);
  }
});

test("malformed and unknown outcomes reject safely and preserve the pending request", () => {
  const values = new Map();
  const storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
  savePendingTurn("game", { id: "original", text: "Original action" }, storage);
  for (const [parser, payload] of [
    [parseView, { ...view, state_version: "1" }], [parseView, { ...view, billing: null }],
    [parseView, { ...view, complete: 0 }], [parseView, { ...view, day: false }],
    [parseView, { ...view, status_fields: [{ id: "x", label: "X", value: 1.5 }] }],
    [parseTurnStreamEvent, { type: "future", ...failure }], [parseTurnStreamEvent, { type: "preview", segments: [] }],
    [parseTurnStreamEvent, { type: "complete", view: { body: "private payload" } }],
    [parseTurnFailure, { commit_state: "not_started", request_id: "original" }],
    [parseTurnFailure, { ...failure, retryable: "false" }],
  ]) {
    assert.throws(() => parser(payload), (error) => error instanceof ContractError && !error.message.includes("private payload"));
    assert.equal(discardUnstartedTurn("game", "original", undefined, storage), false);
    assert.deepEqual(readPendingTurn("game", storage), { id: "original", text: "Original action" });
  }
  assert.equal(discardUnstartedTurn("game", "original", parseTurnFailure(failure), storage), true);
});
