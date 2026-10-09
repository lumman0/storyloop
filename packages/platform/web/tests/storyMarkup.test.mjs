import assert from "node:assert/strict";
import { test } from "node:test";

import { parseStoryInline } from "../src/lib/storyMarkup.ts";

test("renders NPC action markers as emphasis without changing the prose", () => {
  assert.deepEqual(parseStoryInline("早。*稍微停顿了一下。*你吃早饭了吗？"), [
    { kind: "text", text: "早。" },
    { kind: "emphasis", text: "稍微停顿了一下。" },
    { kind: "text", text: "你吃早饭了吗？" },
  ]);
});

test("keeps escaped and unmatched stars as literal text", () => {
  assert.deepEqual(parseStoryInline("\\*旁白\\* 与未闭合的 *动作"), [
    { kind: "text", text: "*旁白* 与未闭合的 *动作" },
  ]);
});

test("supports bold markers while leaving HTML as inert text", () => {
  assert.deepEqual(parseStoryInline("**重要**<script>hi</script>"), [
    { kind: "strong", text: "重要" },
    { kind: "text", text: "<script>hi</script>" },
  ]);
});
