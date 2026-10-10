import type { TurnFailure } from "./contracts";

type TurnStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export type StoredPendingTurn = { id: string; text: string; retryable?: false; error?: string };

export function discardUnstartedTurn(
  gameId: string,
  requestId: string,
  failure: Partial<Pick<TurnFailure, "commit_state" | "request_id">> | undefined,
  storage: TurnStorage = sessionStorage,
): boolean {
  if (failure?.commit_state !== "not_started" || failure.request_id !== requestId) return false;
  clearPendingTurn(gameId, storage);
  return true;
}

function key(gameId: string): string {
  return `storyloop.pending.${gameId}`;
}

export function readPendingTurn(
  gameId: string,
  storage: TurnStorage = sessionStorage,
): StoredPendingTurn | null {
  try {
    const raw = storage.getItem(key(gameId));
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (
      value && typeof value === "object" &&
      "id" in value && typeof value.id === "string" &&
      /^[A-Za-z0-9_-]{1,64}$/.test(value.id) &&
      "text" in value && typeof value.text === "string" && value.text.trim()
    ) {
      const turn: StoredPendingTurn = { id: value.id, text: value.text };
      if ("retryable" in value && value.retryable === false) {
        turn.retryable = false;
        turn.error = "error" in value && typeof value.error === "string" && value.error.trim()
          ? value.error.slice(0, 2000) : "这条行动需要人工恢复，请联系管理员。";
      }
      return turn;
    }
  } catch {
    // An unavailable or damaged tab store cannot prevent the game from loading.
  }
  return null;
}

export function savePendingTurn(
  gameId: string,
  turn: StoredPendingTurn,
  storage: TurnStorage = sessionStorage,
): void {
  try {
    storage.setItem(key(gameId), JSON.stringify(turn));
  } catch {
    // A blocked tab store cannot prevent submitting the turn.
  }
}

export function clearPendingTurn(
  gameId: string,
  storage: TurnStorage = sessionStorage,
): void {
  try {
    storage.removeItem(key(gameId));
  } catch {
    // A blocked tab store cannot prevent showing the completed turn.
  }
}
