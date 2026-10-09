import type { ReviewSubmission, UserScenario } from "./api";

export function scenarioSubmissionState(
  scenario: Pick<UserScenario, "id" | "version_id">, all: ReviewSubmission[],
) {
  const submissions = all.filter((item) => item.scenario_id === scenario.id);
  const pending = submissions.find((item) => item.status === "pending") || null;
  const latest = submissions.find((item) => item.version_id === scenario.version_id) || null;
  return { submissions, pending, latest, canSubmit: !pending && !latest,
    canDelete: submissions.length === 0 };
}
