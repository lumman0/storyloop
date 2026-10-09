import type { ReviewDetail } from "./api";

export type ReviewSelection = {
  request: number; id: string | null; detail: ReviewDetail | null; reason: string; loading: boolean;
};
type Action = { type: "select"; id: string; request: number }
  | { type: "loaded"; request: number; detail: ReviewDetail }
  | { type: "failed"; request: number }
  | { type: "reason"; id: string; reason: string }
  | { type: "clear" };
export const emptyReviewSelection: ReviewSelection = {
  request: 0, id: null, detail: null, reason: "", loading: false,
};
export function reviewSelectionReducer(state: ReviewSelection, action: Action): ReviewSelection {
  if (action.type === "clear") return { ...emptyReviewSelection, request: state.request };
  if (action.type === "select") return {
    request: action.request, id: action.id, detail: null, reason: "", loading: true,
  };
  if (action.type === "reason") return canDecideReview(state) && action.id === state.id
    ? { ...state, reason: action.reason } : state;
  if (action.request !== state.request || !state.id) return state;
  if (action.type === "failed") return { ...state, loading: false };
  if (action.detail.submission_id !== state.id) return state;
  return { ...state, detail: action.detail, loading: false };
}
export function canDecideReview(state: ReviewSelection): boolean {
  return !state.loading && !!state.detail && state.detail.submission_id === state.id
    && state.detail.status === "pending";
}
