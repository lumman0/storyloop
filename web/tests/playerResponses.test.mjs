import assert from "node:assert/strict";
import test from "node:test";
import { ApiError, readTurnStream, responseError } from "../src/lib/playerResponses.ts";
import { savePendingTurn, readPendingTurn, discardUnstartedTurn } from "../src/lib/pendingTurn.ts";

const view = { game_id: "game", catalog_id: "story", mode: "freeform", presentation_mode: "interactive",
  opening: "", body: "Result", segments: [], suggestions: [], action_options: [], status_fields: [],
  interaction: null, tick: 1, state_version: 1, day: null, time_of_day: null, complete: false, turn_id: "original" };
const complete = { type: "complete", view };
const completeFrame = `data: ${JSON.stringify(complete)}\n\n`;

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

for (const [name, field] of [
  ["unspaced bad JSON", "data:{private"],
  ["unspaced unknown event", 'data:{"type":"future","commit_state":"not_started","request_id":"original"}'],
  ["unspaced malformed complete", 'data:{"type":"complete","view":{"body":"private"}}'],
  ["unspaced malformed error", 'data:{"type":"error","commit_state":"not_started","request_id":"original"}'],
  ["bare data", "data"],
  ["empty data without space", "data:"],
  ["empty data with space", "data: "],
]) {
  test(`${name} rejects despite a valid completion and retains the original pending request`, async () => {
    const values = new Map();
    const storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
    for (const frames of [`${field}\n\n${completeFrame}`, `${completeFrame}${field}\n\n`]) {
      savePendingTurn("game", { id: "original", text: "Original action" }, storage);
      const events = [];
      await assert.rejects(readTurnStream(new Response(frames), (event) => events.push(event)), (error) => {
        assert.ok(error instanceof ApiError);
        assert.equal(error.failure, undefined);
        assert.equal(error.message.includes("private"), false);
        assert.equal(discardUnstartedTurn("game", "original", error.failure, storage), false);
        return true;
      });
      assert.deepEqual(events, frames.startsWith(completeFrame) ? [complete] : []);
      assert.deepEqual(readPendingTurn("game", storage), { id: "original", text: "Original action" });
    }
  });
}

test("a valid unspaced completion succeeds while comment and non-data fields are ignored", async () => {
  const events = [];
  const response = new Response(`: keepalive\n\nevent: message\nid: original\n\ndata:${JSON.stringify(complete)}\n\n`);
  assert.deepEqual(await readTurnStream(response, (event) => events.push(event)), view);
  assert.deepEqual(events, [complete]);
});

for (const [name, split] of [["data line", -3], ["blank line", -1]]) {
  test(`a complete CRLF frame succeeds when the ${name} CRLF is split between reader chunks`, async () => {
    const frame = completeFrame.replace(/\n/g, "\r\n");
    const encoder = new TextEncoder();
    const response = new Response(new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(frame.slice(0, split)));
        controller.enqueue(encoder.encode(frame.slice(split)));
        controller.close();
      },
    }));
    const events = [];
    assert.deepEqual(await readTurnStream(response, (event) => events.push(event)), view);
    assert.deepEqual(events, [complete]);
  });
}
