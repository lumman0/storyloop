/* Generated from api/contracts.py. Run npm run contracts:generate. */

export type Code = string;
export type CommitState = "not_started" | "committed" | "unknown";
export type Detail = string;
export type Message = string;
export type RequestId = string | null;
export type Retryable = boolean;

export interface TurnFailure {
  code: Code;
  commit_state: CommitState;
  detail?: Detail;
  message: Message;
  request_id: RequestId;
  retryable: Retryable;
}
