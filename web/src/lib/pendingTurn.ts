type TurnStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export type StoredPendingTurn = { id: string; text: string };

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
    ) return { id: value.id, text: value.text };
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
