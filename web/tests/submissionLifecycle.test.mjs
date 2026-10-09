import assert from "node:assert/strict";
import { test } from "node:test";
import { scenarioSubmissionState } from "../src/lib/submissionLifecycle.ts";

const scenario = { id: "story", version_id: "v2" };
const v1 = { scenario_id: "story", version_id: "v1", submission_id: "s1", status: "pending" };

test("a pending older version stays withdrawable after a newer upload", () => {
  const state = scenarioSubmissionState(scenario, [v1]);
  assert.deepEqual(state.pending, v1);
  assert.equal(state.pending.submission_id, "s1");
  assert.equal(state.canSubmit, false);
  assert.equal(state.latest, null);
});

test("withdrawing the older version unlocks submission of the new version", () => {
  const state = scenarioSubmissionState(scenario, [{ ...v1, status: "withdrawn" }]);
  assert.equal(state.pending, null);
  assert.equal(state.canSubmit, true);
});

test("already submitted versions cannot be resubmitted or deleted", () => {
  for (const status of ["pending", "approved", "rejected", "withdrawn"]) {
    const state = scenarioSubmissionState(scenario, [{ ...v1, version_id: "v2", status }]);
    assert.equal(state.canSubmit, false);
    assert.equal(state.canDelete, false);
  }
  assert.equal(scenarioSubmissionState(scenario, []).canDelete, true);
});

test("another scenario's pending review does not block this scenario", () => {
  const state = scenarioSubmissionState(scenario, [{ ...v1, scenario_id: "another" }]);
  assert.equal(state.canSubmit, true);
  assert.deepEqual(state.submissions, []);
});
