import assert from "node:assert/strict";
import { test } from "node:test";
import { emptyReviewSelection, reviewSelectionReducer, canDecideReview } from "../src/lib/reviewSelection.ts";

const detail = (id) => ({ submission_id: id, status: "pending" });

test("late A response cannot replace B or attach B's reason to A", () => {
  let state = reviewSelectionReducer(emptyReviewSelection, { type: "select", id: "a", request: 1 });
  state = reviewSelectionReducer(state, { type: "select", id: "b", request: 2 });
  assert.equal(state.reason, "");
  assert.equal(canDecideReview(state), false);
  state = reviewSelectionReducer(state, { type: "loaded", request: 2, detail: detail("b") });
  assert.deepEqual(state.detail, detail("b"));
  state = reviewSelectionReducer(state, { type: "reason", id: "b", reason: "B's reason" });
  const selectedB = state;
  assert.equal(reviewSelectionReducer(state, { type: "loaded", request: 1, detail: detail("a") }), selectedB);
  assert.equal(reviewSelectionReducer(state, { type: "failed", request: 1 }), selectedB);
  assert.equal(state.detail.submission_id, "b");
  assert.equal(state.reason, "B's reason");
  assert.equal(canDecideReview(state), true);
});

test("switching selection clears the old detail and reason immediately", () => {
  let state = reviewSelectionReducer(emptyReviewSelection, { type: "select", id: "a", request: 1 });
  state = reviewSelectionReducer(state, { type: "loaded", request: 1, detail: detail("a") });
  state = reviewSelectionReducer(state, { type: "reason", id: "a", reason: "old" });
  assert.equal(state.reason, "old");
  state = reviewSelectionReducer(state, { type: "select", id: "b", request: 2 });
  assert.equal(state.detail, null);
  assert.equal(state.reason, "");
  assert.equal(canDecideReview(state), false);
  assert.equal(reviewSelectionReducer(state, { type: "reason", id: "a", reason: "late" }), state);
});

test("reselecting the same ID still rejects the earlier request", () => {
  let state = reviewSelectionReducer(emptyReviewSelection, { type: "select", id: "a", request: 1 });
  state = reviewSelectionReducer(state, { type: "select", id: "a", request: 2 });
  assert.equal(state.request, 2);
  assert.equal(reviewSelectionReducer(state, { type: "loaded", request: 1, detail: detail("a") }), state);
});

test("clearing selection ignores pending responses and nonpending detail cannot be decided", () => {
  let state = reviewSelectionReducer(emptyReviewSelection, { type: "select", id: "a", request: 1 });
  state = reviewSelectionReducer(state, { type: "clear" });
  assert.equal(reviewSelectionReducer(state, { type: "loaded", request: 1, detail: detail("a") }), state);
  state = reviewSelectionReducer(state, { type: "select", id: "b", request: 2 });
  state = reviewSelectionReducer(state, { type: "loaded", request: 2, detail: { ...detail("b"), status: "withdrawn" } });
  assert.equal(state.detail?.submission_id, "b");
  assert.equal(canDecideReview(state), false);
});
