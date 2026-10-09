import assert from "node:assert/strict";
import test from "node:test";

import { createRequestId } from "../src/lib/requestId.ts";

test("creates a request ID when randomUUID is unavailable on HTTP", () => {
  const insecureContextCrypto = {
    getRandomValues: globalThis.crypto.getRandomValues.bind(globalThis.crypto),
  };

  const id = createRequestId(insecureContextCrypto);

  assert.match(id, /^[0-9a-f]{32}$/);
  assert.notEqual(createRequestId(insecureContextCrypto), id);
});
