import assert from "node:assert/strict";
import { test } from "node:test";

import { clearPendingTurn, readPendingTurn, savePendingTurn } from "../src/lib/pendingTurn.ts";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}

test("an interrupted turn keeps its request ID across a page reload", () => {
  const storage = memoryStorage();
  savePendingTurn("game-a", { id: "request-1", text: "我走向门口" }, storage);
  assert.deepEqual(readPendingTurn("game-a", storage), {
    id: "request-1", text: "我走向门口",
  });
  assert.equal(readPendingTurn("game-b", storage), null);
  clearPendingTurn("game-a", storage);
  assert.equal(readPendingTurn("game-a", storage), null);
});

test("blocked browser storage does not prevent sending a turn", () => {
  const blocked = {
    getItem: () => { throw new Error("storage blocked"); },
    setItem: () => { throw new Error("storage blocked"); },
    removeItem: () => { throw new Error("storage blocked"); },
  };
  assert.doesNotThrow(() => savePendingTurn("game-a", { id: "request-1", text: "你好" }, blocked));
  assert.equal(readPendingTurn("game-a", blocked), null);
  assert.doesNotThrow(() => clearPendingTurn("game-a", blocked));
});
